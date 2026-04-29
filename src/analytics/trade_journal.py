"""Trade journal for comprehensive trade logging and analytics."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Session

from src.models.database import Database
from src.models.orm import Base

logger = logging.getLogger(__name__)


class TradeJournalEntryORM(Base):
    """Trade journal entry ORM model."""
    __tablename__ = "trade_journal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, nullable=False, unique=True, index=True)
    strategy_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=True, index=True)  # 'LONG' or 'SHORT' — needed for correct P&L calculation
    
    # Entry details
    entry_time = Column(DateTime, nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    entry_size = Column(Float, nullable=False)
    entry_reason = Column(String, nullable=False)
    entry_order_id = Column(String, nullable=True)
    
    # Exit details
    exit_time = Column(DateTime, nullable=True, index=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    exit_order_id = Column(String, nullable=True)
    
    # Performance metrics
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    hold_time_hours = Column(Float, nullable=True)
    
    # Execution quality
    max_adverse_excursion = Column(Float, nullable=True)  # MAE - worst drawdown during trade
    max_favorable_excursion = Column(Float, nullable=True)  # MFE - best profit during trade
    entry_slippage = Column(Float, nullable=True)
    exit_slippage = Column(Float, nullable=True)
    
    # Market context
    market_regime = Column(String, nullable=True, index=True)
    sector = Column(String, nullable=True, index=True)
    
    # Fundamental data (if available)
    fundamentals = Column(JSON, nullable=True)
    
    # ML/Conviction scores
    conviction_score = Column(Float, nullable=True)
    ml_confidence = Column(Float, nullable=True)
    
    # Additional metadata
    trade_metadata = Column(JSON, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "trade_id": self.trade_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "entry_price": self.entry_price,
            "entry_size": self.entry_size,
            "entry_reason": self.entry_reason,
            "entry_order_id": self.entry_order_id,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "exit_order_id": self.exit_order_id,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "hold_time_hours": self.hold_time_hours,
            "max_adverse_excursion": self.max_adverse_excursion,
            "max_favorable_excursion": self.max_favorable_excursion,
            "entry_slippage": self.entry_slippage,
            "exit_slippage": self.exit_slippage,
            "market_regime": self.market_regime,
            "sector": self.sector,
            "fundamentals": self.fundamentals,
            "conviction_score": self.conviction_score,
            "ml_confidence": self.ml_confidence,
            "metadata": self.trade_metadata
        }


class TradeJournal:
    """Comprehensive trade journal for logging and analyzing trades."""

    def __init__(self, database: Database):
        """Initialize trade journal.
        
        Args:
            database: Database instance for persistence
        """
        self.database = database
        logger.info("Initialized TradeJournal")

    @staticmethod
    def _resolve_trade_side(order_side: Optional[str], entry_reason: Optional[str]) -> str:
        """Determine trade side (LONG or SHORT) from order side and entry reason.
        
        - BUY order = opening LONG position
        - SELL order = opening SHORT position
        - Falls back to parsing entry_reason for 'short'/'sell' keywords
        """
        if order_side:
            if order_side.upper() == 'SELL':
                return 'SHORT'
            elif order_side.upper() == 'BUY':
                return 'LONG'
        if entry_reason and any(kw in entry_reason.lower() for kw in ('short', 'sell')):
            return 'SHORT'
        return 'LONG'  # Default to LONG for backward compatibility

    def log_entry(
        self,
        trade_id: str,
        strategy_id: str,
        symbol: str,
        entry_time: datetime,
        entry_price: float,
        entry_size: float,
        entry_reason: str,
        entry_order_id: Optional[str] = None,
        market_regime: Optional[str] = None,
        sector: Optional[str] = None,
        fundamentals: Optional[Dict[str, Any]] = None,
        conviction_score: Optional[float] = None,
        ml_confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expected_price: Optional[float] = None,
        order_side: Optional[str] = None
    ) -> None:
        """Log trade entry.
        
        Args:
            trade_id: Unique trade identifier
            strategy_id: Strategy that generated the trade
            symbol: Instrument symbol
            entry_time: Entry timestamp
            entry_price: Entry price (filled price)
            entry_size: Position size
            entry_reason: Reason for entry
            entry_order_id: Order ID for entry
            market_regime: Market regime at entry
            sector: Sector/industry
            fundamentals: Fundamental data at entry
            conviction_score: Conviction score (0-100)
            ml_confidence: ML confidence score (0-1)
            metadata: Additional metadata
            expected_price: Expected price at order creation for slippage calculation
            order_side: Order side ('BUY' or 'SELL') for directional slippage calculation
        """
        logger.info(f"Logging trade entry: {trade_id} - {symbol} @ {entry_price}")

        # Calculate entry slippage if expected_price is available
        entry_slippage_pct = None
        if expected_price and expected_price > 0 and entry_price:
            if order_side and order_side.upper() == "SELL":
                # For sells: positive slippage = sold lower than expected (bad)
                entry_slippage_pct = (expected_price - entry_price) / expected_price
            else:
                # For buys: positive slippage = bought higher than expected (bad)
                entry_slippage_pct = (entry_price - expected_price) / expected_price
            logger.info(
                f"Entry slippage for {trade_id}: {entry_slippage_pct:.4%} "
                f"(expected={expected_price:.4f}, filled={entry_price:.4f}, side={order_side})"
            )

        # Enrich metadata with slippage info
        enriched_metadata = dict(metadata) if metadata else {}
        if entry_slippage_pct is not None:
            enriched_metadata["entry_slippage_pct"] = entry_slippage_pct
        if expected_price is not None:
            enriched_metadata["expected_price"] = expected_price
        if order_side is not None:
            enriched_metadata["order_side"] = order_side

        session = self.database.get_session()
        try:
            # Check for existing entry to avoid UNIQUE constraint violation
            existing = session.query(TradeJournalEntryORM).filter_by(trade_id=trade_id).first()
            if existing:
                logger.info(f"Trade journal entry already exists for {trade_id}, skipping duplicate insert")
                return

            entry = TradeJournalEntryORM(
                trade_id=trade_id,
                strategy_id=strategy_id,
                symbol=symbol,
                side=self._resolve_trade_side(order_side, entry_reason),
                entry_time=entry_time,
                entry_price=entry_price,
                entry_size=entry_size,
                entry_reason=entry_reason,
                entry_order_id=entry_order_id,
                entry_slippage=entry_slippage_pct,
                market_regime=market_regime,
                sector=sector,
                fundamentals=fundamentals,
                conviction_score=conviction_score,
                ml_confidence=ml_confidence,
                trade_metadata=enriched_metadata
            )
            session.add(entry)
            session.commit()
            logger.debug(f"Trade entry logged: {trade_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to log trade entry: {e}")
            raise
        finally:
            session.close()

    def log_exit(
        self,
        trade_id: str,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
        exit_order_id: Optional[str] = None,
        max_adverse_excursion: Optional[float] = None,
        max_favorable_excursion: Optional[float] = None,
        exit_slippage: Optional[float] = None,
        symbol: Optional[str] = None
    ) -> None:
        """Log trade exit and calculate performance metrics.
        
        Args:
            trade_id: Trade identifier
            exit_time: Exit timestamp
            exit_price: Exit price
            exit_reason: Reason for exit
            exit_order_id: Order ID for exit
            max_adverse_excursion: Worst drawdown during trade
            max_favorable_excursion: Best profit during trade
            exit_slippage: Slippage on exit
            symbol: Symbol for fallback lookup when trade_id doesn't match
        """
        logger.info(f"Logging trade exit: {trade_id} @ {exit_price}")

        session = self.database.get_session()
        try:
            entry = session.query(TradeJournalEntryORM).filter_by(trade_id=trade_id).first()
            if not entry:
                # Fallback: trade_id might be a position ID while entry was logged with order ID.
                # Try matching by trade_id stored in entry_order_id, or find the most recent
                # open entry for the same symbol (no exit_time yet).
                entry = (
                    session.query(TradeJournalEntryORM)
                    .filter_by(entry_order_id=str(trade_id))
                    .filter(TradeJournalEntryORM.exit_time.is_(None))
                    .first()
                )
            if not entry and symbol:
                # Last resort: find most recent open entry for this symbol
                entry = (
                    session.query(TradeJournalEntryORM)
                    .filter_by(symbol=symbol)
                    .filter(TradeJournalEntryORM.exit_time.is_(None))
                    .order_by(TradeJournalEntryORM.entry_time.desc())
                    .first()
                )
            if not entry:
                logger.warning(f"Trade entry not found for trade_id={trade_id} — exit not logged")
                return

            # Update exit details
            entry.exit_time = exit_time
            entry.exit_price = exit_price
            entry.exit_reason = exit_reason
            entry.exit_order_id = exit_order_id
            entry.exit_slippage = exit_slippage

            # Calculate performance metrics
            # entry_size is the dollar amount invested (eToro uses dollar-denominated positions)
            # P&L = (price_change / entry_price) * invested_amount
            # Direction-aware: SHORT profits when price drops, LONG profits when price rises
            is_short = entry.side == 'SHORT' if entry.side else False
            if is_short:
                entry.pnl_percent = ((entry.entry_price - exit_price) / entry.entry_price) * 100 if entry.entry_price else 0
            else:
                entry.pnl_percent = ((exit_price - entry.entry_price) / entry.entry_price) * 100 if entry.entry_price else 0
            entry.pnl = (entry.pnl_percent / 100) * entry.entry_size
            entry.hold_time_hours = (exit_time - entry.entry_time).total_seconds() / 3600

            # Update MAE/MFE if provided
            if max_adverse_excursion is not None:
                entry.max_adverse_excursion = max_adverse_excursion
            if max_favorable_excursion is not None:
                entry.max_favorable_excursion = max_favorable_excursion

            session.commit()
            logger.info(
                f"Trade exit logged: {trade_id} - "
                f"P&L: ${entry.pnl:.2f} ({entry.pnl_percent:.2f}%), "
                f"Hold time: {entry.hold_time_hours:.1f}h"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to log trade exit: {e}")
            raise
        finally:
            session.close()

    def update_mae_mfe(
        self,
        trade_id: str,
        current_price: float
    ) -> None:
        """Update MAE/MFE for an open trade.
        
        Args:
            trade_id: Trade identifier
            current_price: Current market price
        """
        session = self.database.get_session()
        try:
            entry = session.query(TradeJournalEntryORM).filter_by(trade_id=trade_id).first()
            if not entry or entry.exit_time is not None:
                return

            # Calculate current P&L (direction-aware)
            is_short = entry.side == 'SHORT' if entry.side else False
            if is_short:
                current_pnl_percent = ((entry.entry_price - current_price) / entry.entry_price) * 100
            else:
                current_pnl_percent = ((current_price - entry.entry_price) / entry.entry_price) * 100

            # Update MAE (worst drawdown)
            if entry.max_adverse_excursion is None or current_pnl_percent < entry.max_adverse_excursion:
                entry.max_adverse_excursion = current_pnl_percent

            # Update MFE (best profit)
            if entry.max_favorable_excursion is None or current_pnl_percent > entry.max_favorable_excursion:
                entry.max_favorable_excursion = current_pnl_percent

            session.commit()
        except Exception as e:
            logger.error(f"Failed to update MAE/MFE for trade {trade_id}: {e}")
            session.rollback()
        finally:
            session.close()

    def get_trade(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """Get trade by ID.
        
        Args:
            trade_id: Trade identifier
            
        Returns:
            Trade data or None if not found
        """
        session = self.database.get_session()
        try:
            entry = session.query(TradeJournalEntryORM).filter_by(trade_id=trade_id).first()
            return entry.to_dict() if entry else None
        finally:
            session.close()

    def get_all_trades(
        self,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        closed_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all trades with optional filters.
        
        Args:
            strategy_id: Filter by strategy
            symbol: Filter by symbol
            start_date: Filter by start date
            end_date: Filter by end date
            closed_only: Only return closed trades
            
        Returns:
            List of trade data
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM)

            if strategy_id:
                query = query.filter_by(strategy_id=strategy_id)
            if symbol:
                query = query.filter_by(symbol=symbol)
            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)
            if closed_only:
                query = query.filter(TradeJournalEntryORM.exit_time.isnot(None))

            entries = query.order_by(TradeJournalEntryORM.entry_time.desc()).all()
            return [entry.to_dict() for entry in entries]
        finally:
            session.close()

    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Get all open trades.
        
        Returns:
            List of open trade data
        """
        session = self.database.get_session()
        try:
            entries = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.is_(None)
            ).all()
            return [entry.to_dict() for entry in entries]
        finally:
            session.close()

    def calculate_win_rate(
        self,
        strategy_id: Optional[str] = None,
        market_regime: Optional[str] = None,
        sector: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> float:
        """Calculate win rate with optional filters.
        
        Args:
            strategy_id: Filter by strategy
            market_regime: Filter by market regime
            sector: Filter by sector
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            Win rate as percentage (0-100)
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None)
            )

            if strategy_id:
                query = query.filter_by(strategy_id=strategy_id)
            if market_regime:
                query = query.filter_by(market_regime=market_regime)
            if sector:
                query = query.filter_by(sector=sector)
            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()
            if not trades:
                return 0.0

            winning_trades = sum(1 for t in trades if t.pnl and t.pnl > 0)
            return (winning_trades / len(trades)) * 100

        finally:
            session.close()

    def calculate_avg_winner_loser(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Calculate average winner and loser amounts.
        
        Args:
            strategy_id: Filter by strategy
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            Dictionary with avg_winner and avg_loser
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.pnl.isnot(None)
            )

            if strategy_id:
                query = query.filter_by(strategy_id=strategy_id)
            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()
            if not trades:
                return {"avg_winner": 0.0, "avg_loser": 0.0}

            winners = [t.pnl for t in trades if t.pnl > 0]
            losers = [t.pnl for t in trades if t.pnl < 0]

            avg_winner = sum(winners) / len(winners) if winners else 0.0
            avg_loser = sum(losers) / len(losers) if losers else 0.0

            return {
                "avg_winner": avg_winner,
                "avg_loser": avg_loser
            }

        finally:
            session.close()

    def calculate_profit_factor(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> float:
        """Calculate profit factor (gross profit / gross loss).
        
        Args:
            strategy_id: Filter by strategy
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            Profit factor
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.pnl.isnot(None)
            )

            if strategy_id:
                query = query.filter_by(strategy_id=strategy_id)
            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()
            if not trades:
                return 0.0

            gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
            gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))

            if gross_loss == 0:
                return float('inf') if gross_profit > 0 else 0.0

            return gross_profit / gross_loss

        finally:
            session.close()

    def calculate_avg_hold_time(
        self,
        strategy_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> float:
        """Calculate average holding period in hours.
        
        Args:
            strategy_id: Filter by strategy
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            Average hold time in hours
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.hold_time_hours.isnot(None)
            )

            if strategy_id:
                query = query.filter_by(strategy_id=strategy_id)
            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()
            if not trades:
                return 0.0

            return sum(t.hold_time_hours for t in trades) / len(trades)

        finally:
            session.close()

    def get_performance_by_strategy(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get performance metrics grouped by strategy.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of strategy performance metrics
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None)
            )

            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()

            # Group by strategy
            strategy_trades = {}
            for trade in trades:
                if trade.strategy_id not in strategy_trades:
                    strategy_trades[trade.strategy_id] = []
                strategy_trades[trade.strategy_id].append(trade)

            # Calculate metrics for each strategy
            results = []
            for strategy_id, strat_trades in strategy_trades.items():
                total_trades = len(strat_trades)
                winning_trades = sum(1 for t in strat_trades if t.pnl and t.pnl > 0)
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

                total_pnl = sum(t.pnl for t in strat_trades if t.pnl)
                avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

                winners = [t.pnl for t in strat_trades if t.pnl and t.pnl > 0]
                losers = [t.pnl for t in strat_trades if t.pnl and t.pnl < 0]

                avg_winner = sum(winners) / len(winners) if winners else 0
                avg_loser = sum(losers) / len(losers) if losers else 0

                gross_profit = sum(winners) if winners else 0
                gross_loss = abs(sum(losers)) if losers else 0
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

                results.append({
                    "strategy_id": strategy_id,
                    "total_trades": total_trades,
                    "win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "avg_pnl": avg_pnl,
                    "avg_winner": avg_winner,
                    "avg_loser": avg_loser,
                    "profit_factor": profit_factor
                })

            return results

        finally:
            session.close()

    def get_performance_by_regime(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get performance metrics grouped by market regime.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of regime performance metrics
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.market_regime.isnot(None)
            )

            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()

            # Group by regime
            regime_trades = {}
            for trade in trades:
                if trade.market_regime not in regime_trades:
                    regime_trades[trade.market_regime] = []
                regime_trades[trade.market_regime].append(trade)

            # Calculate metrics for each regime
            results = []
            for regime, reg_trades in regime_trades.items():
                total_trades = len(reg_trades)
                winning_trades = sum(1 for t in reg_trades if t.pnl and t.pnl > 0)
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

                total_pnl = sum(t.pnl for t in reg_trades if t.pnl)
                avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

                results.append({
                    "market_regime": regime,
                    "total_trades": total_trades,
                    "win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "avg_pnl": avg_pnl
                })

            return results

        finally:
            session.close()

    def get_performance_by_sector(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get performance metrics grouped by sector.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of sector performance metrics
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.sector.isnot(None)
            )

            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()

            # Group by sector
            sector_trades = {}
            for trade in trades:
                if trade.sector not in sector_trades:
                    sector_trades[trade.sector] = []
                sector_trades[trade.sector].append(trade)

            # Calculate metrics for each sector
            results = []
            for sector, sec_trades in sector_trades.items():
                total_trades = len(sec_trades)
                winning_trades = sum(1 for t in sec_trades if t.pnl and t.pnl > 0)
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

                total_pnl = sum(t.pnl for t in sec_trades if t.pnl)
                avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

                results.append({
                    "sector": sector,
                    "total_trades": total_trades,
                    "win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "avg_pnl": avg_pnl
                })

            return results

        finally:
            session.close()

    def get_performance_by_hold_period(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get performance metrics grouped by holding period buckets.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of hold period performance metrics
        """
        session = self.database.get_session()
        try:
            query = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.hold_time_hours.isnot(None)
            )

            if start_date:
                query = query.filter(TradeJournalEntryORM.entry_time >= start_date)
            if end_date:
                query = query.filter(TradeJournalEntryORM.entry_time <= end_date)

            trades = query.all()

            # Define hold period buckets (in hours)
            buckets = [
                ("< 1 day", 0, 24),
                ("1-3 days", 24, 72),
                ("3-7 days", 72, 168),
                ("1-2 weeks", 168, 336),
                ("2-4 weeks", 336, 672),
                ("> 4 weeks", 672, float('inf'))
            ]

            # Group trades by bucket
            bucket_trades = {name: [] for name, _, _ in buckets}
            for trade in trades:
                for name, min_hours, max_hours in buckets:
                    if min_hours <= trade.hold_time_hours < max_hours:
                        bucket_trades[name].append(trade)
                        break

            # Calculate metrics for each bucket
            results = []
            for name, _, _ in buckets:
                bucket_list = bucket_trades[name]
                if not bucket_list:
                    continue

                total_trades = len(bucket_list)
                winning_trades = sum(1 for t in bucket_list if t.pnl and t.pnl > 0)
                win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

                total_pnl = sum(t.pnl for t in bucket_list if t.pnl)
                avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

                results.append({
                    "hold_period": name,
                    "total_trades": total_trades,
                    "win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "avg_pnl": avg_pnl
                })

            return results

        finally:
            session.close()

    def identify_best_patterns(
        self,
        min_trades: int = 5,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Identify best performing patterns.
        
        Args:
            min_trades: Minimum trades required for pattern
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of best performing patterns
        """
        patterns = []

        # Best strategies
        strategy_perf = self.get_performance_by_strategy(start_date, end_date)
        for perf in strategy_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] > 60:
                patterns.append({
                    "pattern_type": "strategy",
                    "pattern": perf["strategy_id"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"],
                    "profit_factor": perf["profit_factor"]
                })

        # Best regimes
        regime_perf = self.get_performance_by_regime(start_date, end_date)
        for perf in regime_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] > 60:
                patterns.append({
                    "pattern_type": "regime",
                    "pattern": perf["market_regime"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"]
                })

        # Best sectors
        sector_perf = self.get_performance_by_sector(start_date, end_date)
        for perf in sector_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] > 60:
                patterns.append({
                    "pattern_type": "sector",
                    "pattern": perf["sector"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"]
                })

        # Best hold periods
        hold_perf = self.get_performance_by_hold_period(start_date, end_date)
        for perf in hold_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] > 60:
                patterns.append({
                    "pattern_type": "hold_period",
                    "pattern": perf["hold_period"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"]
                })

        # Sort by win rate
        patterns.sort(key=lambda x: x["win_rate"], reverse=True)

        return patterns

    def identify_worst_patterns(
        self,
        min_trades: int = 5,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Identify worst performing patterns.
        
        Args:
            min_trades: Minimum trades required for pattern
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of worst performing patterns
        """
        patterns = []

        # Worst strategies
        strategy_perf = self.get_performance_by_strategy(start_date, end_date)
        for perf in strategy_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] < 40:
                patterns.append({
                    "pattern_type": "strategy",
                    "pattern": perf["strategy_id"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"],
                    "profit_factor": perf["profit_factor"]
                })

        # Worst regimes
        regime_perf = self.get_performance_by_regime(start_date, end_date)
        for perf in regime_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] < 40:
                patterns.append({
                    "pattern_type": "regime",
                    "pattern": perf["market_regime"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"]
                })

        # Worst sectors
        sector_perf = self.get_performance_by_sector(start_date, end_date)
        for perf in sector_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] < 40:
                patterns.append({
                    "pattern_type": "sector",
                    "pattern": perf["sector"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"]
                })

        # Worst hold periods
        hold_perf = self.get_performance_by_hold_period(start_date, end_date)
        for perf in hold_perf:
            if perf["total_trades"] >= min_trades and perf["win_rate"] < 40:
                patterns.append({
                    "pattern_type": "hold_period",
                    "pattern": perf["hold_period"],
                    "win_rate": perf["win_rate"],
                    "total_trades": perf["total_trades"],
                    "avg_pnl": perf["avg_pnl"]
                })

        # Sort by win rate (ascending)
        patterns.sort(key=lambda x: x["win_rate"])

        return patterns

    def generate_insights(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Generate actionable insights from trade data.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            Dictionary of insights and recommendations
        """
        best_patterns = self.identify_best_patterns(min_trades=5, start_date=start_date, end_date=end_date)
        worst_patterns = self.identify_worst_patterns(min_trades=5, start_date=start_date, end_date=end_date)

        # Generate recommendations
        recommendations = []

        # Strategy recommendations
        best_strategies = [p for p in best_patterns if p["pattern_type"] == "strategy"]
        worst_strategies = [p for p in worst_patterns if p["pattern_type"] == "strategy"]

        if best_strategies:
            recommendations.append({
                "type": "increase_allocation",
                "target": best_strategies[0]["pattern"],
                "reason": f"High win rate ({best_strategies[0]['win_rate']:.1f}%) with {best_strategies[0]['total_trades']} trades"
            })

        if worst_strategies:
            recommendations.append({
                "type": "reduce_allocation",
                "target": worst_strategies[0]["pattern"],
                "reason": f"Low win rate ({worst_strategies[0]['win_rate']:.1f}%) with {worst_strategies[0]['total_trades']} trades"
            })

        # Regime recommendations
        best_regimes = [p for p in best_patterns if p["pattern_type"] == "regime"]
        worst_regimes = [p for p in worst_patterns if p["pattern_type"] == "regime"]

        if best_regimes:
            recommendations.append({
                "type": "favor_regime",
                "target": best_regimes[0]["pattern"],
                "reason": f"Strong performance in {best_regimes[0]['pattern']} regime ({best_regimes[0]['win_rate']:.1f}% win rate)"
            })

        if worst_regimes:
            recommendations.append({
                "type": "avoid_regime",
                "target": worst_regimes[0]["pattern"],
                "reason": f"Weak performance in {worst_regimes[0]['pattern']} regime ({worst_regimes[0]['win_rate']:.1f}% win rate)"
            })

        # Hold period recommendations
        best_hold = [p for p in best_patterns if p["pattern_type"] == "hold_period"]
        if best_hold:
            recommendations.append({
                "type": "optimize_hold_period",
                "target": best_hold[0]["pattern"],
                "reason": f"Best performance with {best_hold[0]['pattern']} holding period ({best_hold[0]['win_rate']:.1f}% win rate)"
            })

        return {
            "best_patterns": best_patterns[:5],
            "worst_patterns": worst_patterns[:5],
            "recommendations": recommendations
        }

    def generate_monthly_report(
        self,
        year: int,
        month: int
    ) -> Dict[str, Any]:
        """Generate comprehensive monthly performance report.
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            Monthly report data
        """
        from datetime import date
        from calendar import monthrange

        # Calculate date range
        start_date = datetime(year, month, 1)
        last_day = monthrange(year, month)[1]
        end_date = datetime(year, month, last_day, 23, 59, 59)

        # Get all closed trades for the month
        trades = self.get_all_trades(
            start_date=start_date,
            end_date=end_date,
            closed_only=True
        )

        if not trades:
            return {
                "period": f"{year}-{month:02d}",
                "total_trades": 0,
                "message": "No trades closed in this period"
            }

        # Calculate overall metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["pnl"] and t["pnl"] > 0)
        losing_trades = sum(1 for t in trades if t["pnl"] and t["pnl"] < 0)
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        total_pnl = sum(t["pnl"] for t in trades if t["pnl"])
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

        winners = [t["pnl"] for t in trades if t["pnl"] and t["pnl"] > 0]
        losers = [t["pnl"] for t in trades if t["pnl"] and t["pnl"] < 0]

        avg_winner = sum(winners) / len(winners) if winners else 0
        avg_loser = sum(losers) / len(losers) if losers else 0

        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Calculate average hold time
        hold_times = [t["hold_time_hours"] for t in trades if t["hold_time_hours"]]
        avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0

        # Get performance by strategy
        strategy_performance = self.get_performance_by_strategy(start_date, end_date)

        # Get performance by regime
        regime_performance = self.get_performance_by_regime(start_date, end_date)

        # Get insights
        insights = self.generate_insights(start_date, end_date)

        return {
            "period": f"{year}-{month:02d}",
            "summary": {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "avg_winner": avg_winner,
                "avg_loser": avg_loser,
                "profit_factor": profit_factor,
                "avg_hold_time_hours": avg_hold_time
            },
            "strategy_performance": strategy_performance,
            "regime_performance": regime_performance,
            "insights": insights,
            "trades": trades
        }

    def export_to_csv(
        self,
        filepath: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> None:
        """Export trade history to CSV file.
        
        Args:
            filepath: Output CSV file path
            start_date: Filter by start date
            end_date: Filter by end date
        """
        import csv

        trades = self.get_all_trades(
            start_date=start_date,
            end_date=end_date,
            closed_only=True
        )

        if not trades:
            logger.warning("No trades to export")
            return

        # Define CSV columns
        columns = [
            "trade_id", "strategy_id", "symbol",
            "entry_time", "entry_price", "entry_size", "entry_reason",
            "exit_time", "exit_price", "exit_reason",
            "pnl", "pnl_percent", "hold_time_hours",
            "max_adverse_excursion", "max_favorable_excursion",
            "entry_slippage", "exit_slippage",
            "market_regime", "sector",
            "conviction_score", "ml_confidence"
        ]

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columns)
            writer.writeheader()

            for trade in trades:
                row = {col: trade.get(col) for col in columns}
                writer.writerow(row)

        logger.info(f"Exported {len(trades)} trades to {filepath}")

    def get_equity_curve(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Calculate equity curve over time.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of equity curve points
        """
        trades = self.get_all_trades(
            start_date=start_date,
            end_date=end_date,
            closed_only=True
        )

        if not trades:
            return []

        # Sort by exit time
        trades.sort(key=lambda t: t["exit_time"])

        # Calculate cumulative P&L
        equity_curve = []
        cumulative_pnl = 0.0

        for trade in trades:
            if trade["pnl"]:
                cumulative_pnl += trade["pnl"]
                equity_curve.append({
                    "timestamp": trade["exit_time"],
                    "cumulative_pnl": cumulative_pnl,
                    "trade_id": trade["trade_id"],
                    "symbol": trade["symbol"],
                    "pnl": trade["pnl"]
                })

        return equity_curve

    def get_drawdown_curve(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Calculate drawdown curve over time.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            List of drawdown curve points
        """
        equity_curve = self.get_equity_curve(start_date, end_date)

        if not equity_curve:
            return []

        drawdown_curve = []
        peak = 0.0

        for point in equity_curve:
            cumulative_pnl = point["cumulative_pnl"]

            # Update peak
            if cumulative_pnl > peak:
                peak = cumulative_pnl

            # Calculate drawdown
            drawdown = peak - cumulative_pnl
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0

            drawdown_curve.append({
                "timestamp": point["timestamp"],
                "drawdown": drawdown,
                "drawdown_pct": drawdown_pct,
                "peak": peak
            })

        return drawdown_curve

    def get_win_loss_distribution(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get distribution of wins and losses.
        
        Args:
            start_date: Filter by start date
            end_date: Filter by end date
            
        Returns:
            Win/loss distribution data
        """
        trades = self.get_all_trades(
            start_date=start_date,
            end_date=end_date,
            closed_only=True
        )

        if not trades:
            return {"winners": [], "losers": []}

        winners = [t["pnl"] for t in trades if t["pnl"] and t["pnl"] > 0]
        losers = [t["pnl"] for t in trades if t["pnl"] and t["pnl"] < 0]

        return {
            "winners": winners,
            "losers": losers,
            "winner_count": len(winners),
            "loser_count": len(losers),
            "avg_winner": sum(winners) / len(winners) if winners else 0,
            "avg_loser": sum(losers) / len(losers) if losers else 0,
            "max_winner": max(winners) if winners else 0,
            "max_loser": min(losers) if losers else 0
        }

    def get_performance_feedback(
        self,
        lookback_days: int = 60,
        min_trades: int = 5
    ) -> Dict[str, Any]:
        """Analyze recent trade performance to generate feedback for the strategy proposer.

        Returns template-type win rates, symbol performance rankings, and
        regime-specific performance data that can be used to adjust future
        strategy proposals.

        Args:
            lookback_days: How many days back to analyze (default 60).
            min_trades: Minimum trades required before producing feedback
                for a given group (default 5).

        Returns:
            Dictionary with keys:
                - template_performance: dict mapping template type to metrics
                - symbol_performance: dict mapping symbol to metrics
                - regime_performance: dict mapping regime to metrics
                - total_trades: int, total closed trades in the window
                - has_sufficient_data: bool, whether enough data exists
        """
        start_date = datetime.now() - timedelta(days=lookback_days)

        session = self.database.get_session()
        try:
            trades = (
                session.query(TradeJournalEntryORM)
                .filter(
                    TradeJournalEntryORM.exit_time.isnot(None),
                    TradeJournalEntryORM.entry_time >= start_date,
                )
                .all()
            )

            total_trades = len(trades)
            has_sufficient_data = total_trades >= min_trades

            if not has_sufficient_data:
                logger.info(
                    f"Performance feedback: only {total_trades} closed trades "
                    f"in last {lookback_days} days (need {min_trades}), skipping"
                )
                return {
                    "template_performance": {},
                    "symbol_performance": {},
                    "regime_performance": {},
                    "total_trades": total_trades,
                    "has_sufficient_data": False,
                }

            # --- Template type performance ---
            template_groups: Dict[str, list] = {}
            for trade in trades:
                meta = trade.trade_metadata or {}
                template_type = meta.get("template_type") or meta.get("strategy_type") or "unknown"
                template_groups.setdefault(template_type, []).append(trade)

            template_performance: Dict[str, Dict[str, Any]] = {}
            for ttype, ttrades in template_groups.items():
                n = len(ttrades)
                if n < min_trades:
                    continue
                wins = sum(1 for t in ttrades if t.pnl and t.pnl > 0)
                total_pnl = sum(t.pnl for t in ttrades if t.pnl)
                avg_return = (
                    sum(t.pnl_percent for t in ttrades if t.pnl_percent is not None) / n
                    if any(t.pnl_percent is not None for t in ttrades)
                    else 0.0
                )
                template_performance[ttype] = {
                    "total_trades": n,
                    "win_rate": (wins / n) * 100,
                    "total_pnl": total_pnl,
                    "avg_return_pct": avg_return,
                }

            # --- Symbol performance ---
            symbol_groups: Dict[str, list] = {}
            for trade in trades:
                symbol_groups.setdefault(trade.symbol, []).append(trade)

            symbol_performance: Dict[str, Dict[str, Any]] = {}
            for sym, strades in symbol_groups.items():
                n = len(strades)
                if n < min_trades:
                    continue
                wins = sum(1 for t in strades if t.pnl and t.pnl > 0)
                total_pnl = sum(t.pnl for t in strades if t.pnl)
                avg_return = (
                    sum(t.pnl_percent for t in strades if t.pnl_percent is not None) / n
                    if any(t.pnl_percent is not None for t in strades)
                    else 0.0
                )
                symbol_performance[sym] = {
                    "total_trades": n,
                    "win_rate": (wins / n) * 100,
                    "total_pnl": total_pnl,
                    "avg_return_pct": avg_return,
                }

            # --- Regime performance ---
            regime_groups: Dict[str, list] = {}
            for trade in trades:
                regime = trade.market_regime or "unknown"
                regime_groups.setdefault(regime, []).append(trade)

            regime_performance: Dict[str, Dict[str, Any]] = {}
            for regime, rtrades in regime_groups.items():
                n = len(rtrades)
                if n < min_trades:
                    continue
                wins = sum(1 for t in rtrades if t.pnl and t.pnl > 0)
                total_pnl = sum(t.pnl for t in rtrades if t.pnl)

                # Which template types work best in this regime?
                regime_template_wins: Dict[str, Dict[str, int]] = {}
                for t in rtrades:
                    meta = t.trade_metadata or {}
                    tt = meta.get("template_type") or meta.get("strategy_type") or "unknown"
                    entry = regime_template_wins.setdefault(tt, {"wins": 0, "total": 0})
                    entry["total"] += 1
                    if t.pnl and t.pnl > 0:
                        entry["wins"] += 1

                best_templates = {
                    k: (v["wins"] / v["total"]) * 100
                    for k, v in regime_template_wins.items()
                    if v["total"] >= max(2, min_trades // 2)
                }

                regime_performance[regime] = {
                    "total_trades": n,
                    "win_rate": (wins / n) * 100,
                    "total_pnl": total_pnl,
                    "best_template_win_rates": best_templates,
                }

            # --- Slippage analytics ---
            slippage_analytics = self._calculate_slippage_analytics(trades)

            logger.info(
                f"Performance feedback: {total_trades} trades in last {lookback_days} days, "
                f"{len(template_performance)} template types, "
                f"{len(symbol_performance)} symbols, "
                f"{len(regime_performance)} regimes analyzed"
            )

            return {
                "template_performance": template_performance,
                "symbol_performance": symbol_performance,
                "regime_performance": regime_performance,
                "slippage_analytics": slippage_analytics,
                "total_trades": total_trades,
                "has_sufficient_data": True,
            }

        finally:
            session.close()

    def get_fast_performance_feedback(self, lookback_days: int = 5, min_trades: int = 3) -> Dict[str, Any]:
        """
        Fast 5-day performance feedback for real-time template weight suppression.

        Runs every autonomous cycle to detect template families that are currently
        underperforming. Unlike the 60-day feedback (which adjusts long-term weights),
        this produces a suppression multiplier (0.1-1.0) applied immediately to
        proposal weights for the current cycle.

        A template with < 30% win rate over the last 5 days gets a 0.1 multiplier —
        it can still be proposed but at 10% of normal weight. This means ATR Dynamic
        Trend Follow would be suppressed after 2 days of a correction, not 7.

        Returns:
            Dict with 'template_suppression': {template_name: multiplier (0.1-1.0)}
        """
        start_date = datetime.now() - timedelta(days=lookback_days)
        session = self.database.get_session()
        try:
            from src.models.orm import PositionORM, StrategyORM
            # Use positions table directly — faster than trade journal for recent data
            recent_closed = (
                session.query(PositionORM, StrategyORM)
                .join(StrategyORM, PositionORM.strategy_id == StrategyORM.id)
                .filter(
                    PositionORM.closed_at >= start_date,
                    PositionORM.realized_pnl.isnot(None),
                )
                .all()
            )

            if len(recent_closed) < min_trades:
                return {"template_suppression": {}, "total_trades": len(recent_closed)}

            # Group by template name
            template_groups: Dict[str, list] = {}
            for pos, strat in recent_closed:
                meta = strat.strategy_metadata or {}
                tmpl = meta.get('template_name', '')
                if tmpl:
                    template_groups.setdefault(tmpl, []).append(pos.realized_pnl or 0)

            suppression: Dict[str, float] = {}
            for tmpl, pnls in template_groups.items():
                if len(pnls) < min_trades:
                    continue
                wins = sum(1 for p in pnls if p > 0)
                wr = wins / len(pnls)
                total_pnl = sum(pnls)

                if wr < 0.25 or total_pnl < -500:
                    # Severely underperforming — suppress to 10%
                    suppression[tmpl] = 0.1
                    logger.info(
                        f"Fast feedback: suppressing {tmpl} to 10% weight "
                        f"(win rate {wr:.0%}, P&L ${total_pnl:.0f} over {len(pnls)} trades in {lookback_days}d)"
                    )
                elif wr < 0.35 or total_pnl < -200:
                    # Underperforming — suppress to 40%
                    suppression[tmpl] = 0.4
                    logger.info(
                        f"Fast feedback: reducing {tmpl} to 40% weight "
                        f"(win rate {wr:.0%}, P&L ${total_pnl:.0f} over {len(pnls)} trades in {lookback_days}d)"
                    )
                elif wr > 0.65 and total_pnl > 200:
                    # Outperforming — boost to 150%
                    suppression[tmpl] = 1.5
                    logger.info(
                        f"Fast feedback: boosting {tmpl} to 150% weight "
                        f"(win rate {wr:.0%}, P&L ${total_pnl:.0f} over {len(pnls)} trades in {lookback_days}d)"
                    )

            return {
                "template_suppression": suppression,
                "total_trades": len(recent_closed),
                "lookback_days": lookback_days,
            }

        except Exception as e:
            logger.warning(f"Fast performance feedback failed: {e}")
            return {"template_suppression": {}, "total_trades": 0}
        finally:
            session.close()

    def _calculate_slippage_analytics(
        self, trades: List["TradeJournalEntryORM"]
    ) -> Dict[str, Any]:
        """Calculate slippage analytics from a list of trades.

        Args:
            trades: List of closed trade journal entries.

        Returns:
            Dictionary with slippage metrics:
                - avg_slippage_pct: overall average entry slippage %
                - slippage_by_symbol: avg slippage per symbol
                - slippage_by_hour: avg slippage per hour of day
                - total_slippage_cost_pct: total slippage cost as % of gross returns
                - trades_with_slippage: count of trades that have slippage data
        """
        trades_with_slippage = [
            t for t in trades
            if t.entry_slippage is not None
        ]

        if not trades_with_slippage:
            return {
                "avg_slippage_pct": 0.0,
                "slippage_by_symbol": {},
                "slippage_by_hour": {},
                "total_slippage_cost_pct": 0.0,
                "trades_with_slippage": 0,
            }

        # Overall average slippage
        avg_slippage = sum(t.entry_slippage for t in trades_with_slippage) / len(trades_with_slippage)

        # Slippage by symbol
        symbol_slippages: Dict[str, List[float]] = {}
        for t in trades_with_slippage:
            symbol_slippages.setdefault(t.symbol, []).append(t.entry_slippage)

        slippage_by_symbol = {
            sym: sum(vals) / len(vals)
            for sym, vals in symbol_slippages.items()
        }

        # Slippage by hour of day
        hour_slippages: Dict[int, List[float]] = {}
        for t in trades_with_slippage:
            if t.entry_time:
                hour = t.entry_time.hour
                hour_slippages.setdefault(hour, []).append(t.entry_slippage)

        slippage_by_hour = {
            hour: sum(vals) / len(vals)
            for hour, vals in sorted(hour_slippages.items())
        }

        # Total slippage cost as % of gross returns
        gross_returns = sum(abs(t.pnl_percent) for t in trades if t.pnl_percent)
        total_slippage_pct = sum(abs(t.entry_slippage) for t in trades_with_slippage)
        slippage_cost_pct = (total_slippage_pct / gross_returns * 100) if gross_returns > 0 else 0.0

        return {
            "avg_slippage_pct": avg_slippage,
            "slippage_by_symbol": slippage_by_symbol,
            "slippage_by_hour": slippage_by_hour,
            "total_slippage_cost_pct": slippage_cost_pct,
            "trades_with_slippage": len(trades_with_slippage),
        }

