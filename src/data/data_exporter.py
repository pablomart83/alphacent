"""Data export functionality for strategies, orders, positions, and performance metrics."""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models import (
    AccountInfoORM,
    MarketDataORM,
    OrderORM,
    PositionORM,
    StrategyORM,
    TradingSignalORM,
)
from src.models.database import Database

logger = logging.getLogger(__name__)


class DataExporter:
    """Exports data to CSV and JSON formats."""

    def __init__(self, database: Database, export_dir: str = "exports"):
        """Initialize data exporter.
        
        Args:
            database: Database instance
            export_dir: Directory for exported files
        """
        self.database = database
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Data exporter initialized at {self.export_dir}")

    def export_strategies(
        self,
        format: str = "json",
        output_file: Optional[str] = None
    ) -> Path:
        """Export all strategies.
        
        Args:
            format: Export format ('json' or 'csv')
            output_file: Custom output filename (optional)
            
        Returns:
            Path to exported file
        """
        session = self.database.get_session()
        try:
            strategies = session.query(StrategyORM).all()
            
            if format == "json":
                return self._export_strategies_json(strategies, output_file)
            elif format == "csv":
                return self._export_strategies_csv(strategies, output_file)
            else:
                raise ValueError(f"Unsupported format: {format}")
        finally:
            session.close()

    def export_orders(
        self,
        format: str = "json",
        output_file: Optional[str] = None,
        strategy_id: Optional[str] = None
    ) -> Path:
        """Export orders.
        
        Args:
            format: Export format ('json' or 'csv')
            output_file: Custom output filename (optional)
            strategy_id: Filter by strategy ID (optional)
            
        Returns:
            Path to exported file
        """
        session = self.database.get_session()
        try:
            query = session.query(OrderORM)
            if strategy_id:
                query = query.filter(OrderORM.strategy_id == strategy_id)
            
            orders = query.all()
            
            if format == "json":
                return self._export_orders_json(orders, output_file)
            elif format == "csv":
                return self._export_orders_csv(orders, output_file)
            else:
                raise ValueError(f"Unsupported format: {format}")
        finally:
            session.close()

    def export_positions(
        self,
        format: str = "json",
        output_file: Optional[str] = None,
        strategy_id: Optional[str] = None,
        include_closed: bool = True
    ) -> Path:
        """Export positions.
        
        Args:
            format: Export format ('json' or 'csv')
            output_file: Custom output filename (optional)
            strategy_id: Filter by strategy ID (optional)
            include_closed: Include closed positions
            
        Returns:
            Path to exported file
        """
        session = self.database.get_session()
        try:
            query = session.query(PositionORM)
            if strategy_id:
                query = query.filter(PositionORM.strategy_id == strategy_id)
            if not include_closed:
                query = query.filter(PositionORM.closed_at.is_(None))
            
            positions = query.all()
            
            if format == "json":
                return self._export_positions_json(positions, output_file)
            elif format == "csv":
                return self._export_positions_csv(positions, output_file)
            else:
                raise ValueError(f"Unsupported format: {format}")
        finally:
            session.close()

    def export_performance_metrics(
        self,
        format: str = "json",
        output_file: Optional[str] = None
    ) -> Path:
        """Export performance metrics for all strategies.
        
        Args:
            format: Export format ('json' or 'csv')
            output_file: Custom output filename (optional)
            
        Returns:
            Path to exported file
        """
        session = self.database.get_session()
        try:
            strategies = session.query(StrategyORM).all()
            
            # Extract performance metrics
            metrics = []
            for strategy in strategies:
                metric = {
                    "strategy_id": strategy.id,
                    "strategy_name": strategy.name,
                    "status": strategy.status.value,
                    **strategy.performance
                }
                metrics.append(metric)
            
            if format == "json":
                return self._export_json(metrics, output_file or "performance_metrics.json")
            elif format == "csv":
                return self._export_csv(metrics, output_file or "performance_metrics.csv")
            else:
                raise ValueError(f"Unsupported format: {format}")
        finally:
            session.close()

    def export_all(
        self,
        format: str = "json",
        output_dir: Optional[str] = None
    ) -> Dict[str, Path]:
        """Export all data (strategies, orders, positions, performance).
        
        Args:
            format: Export format ('json' or 'csv')
            output_dir: Custom output directory (optional)
            
        Returns:
            Dictionary mapping data type to exported file path
        """
        if output_dir:
            original_export_dir = self.export_dir
            self.export_dir = Path(output_dir)
            self.export_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            exports = {
                "strategies": self.export_strategies(
                    format=format,
                    output_file=f"strategies_{timestamp}.{format}"
                ),
                "orders": self.export_orders(
                    format=format,
                    output_file=f"orders_{timestamp}.{format}"
                ),
                "positions": self.export_positions(
                    format=format,
                    output_file=f"positions_{timestamp}.{format}"
                ),
                "performance": self.export_performance_metrics(
                    format=format,
                    output_file=f"performance_{timestamp}.{format}"
                )
            }
            
            logger.info(f"Exported all data to {self.export_dir}")
            return exports
        finally:
            if output_dir:
                self.export_dir = original_export_dir

    def _export_strategies_json(
        self,
        strategies: List[StrategyORM],
        output_file: Optional[str]
    ) -> Path:
        """Export strategies to JSON."""
        data = []
        for strategy in strategies:
            data.append({
                "id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "status": strategy.status.value,
                "rules": strategy.rules,
                "symbols": strategy.symbols,
                "risk_params": strategy.risk_params,
                "created_at": strategy.created_at.isoformat(),
                "activated_at": strategy.activated_at.isoformat() if strategy.activated_at else None,
                "retired_at": strategy.retired_at.isoformat() if strategy.retired_at else None,
                "performance": strategy.performance
            })
        
        return self._export_json(data, output_file or "strategies.json")

    def _export_strategies_csv(
        self,
        strategies: List[StrategyORM],
        output_file: Optional[str]
    ) -> Path:
        """Export strategies to CSV."""
        data = []
        for strategy in strategies:
            row = {
                "id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "status": strategy.status.value,
                "symbols": ",".join(strategy.symbols),
                "created_at": strategy.created_at.isoformat(),
                "activated_at": strategy.activated_at.isoformat() if strategy.activated_at else "",
                "retired_at": strategy.retired_at.isoformat() if strategy.retired_at else "",
                # Flatten performance metrics
                **{f"perf_{k}": v for k, v in strategy.performance.items()}
            }
            data.append(row)
        
        return self._export_csv(data, output_file or "strategies.csv")

    def _export_orders_json(
        self,
        orders: List[OrderORM],
        output_file: Optional[str]
    ) -> Path:
        """Export orders to JSON."""
        data = []
        for order in orders:
            data.append({
                "id": order.id,
                "strategy_id": order.strategy_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "status": order.status.value,
                "price": order.price,
                "stop_price": order.stop_price,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "filled_price": order.filled_price,
                "filled_quantity": order.filled_quantity,
                "etoro_order_id": order.etoro_order_id
            })
        
        return self._export_json(data, output_file or "orders.json")

    def _export_orders_csv(
        self,
        orders: List[OrderORM],
        output_file: Optional[str]
    ) -> Path:
        """Export orders to CSV."""
        data = []
        for order in orders:
            data.append({
                "id": order.id,
                "strategy_id": order.strategy_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "status": order.status.value,
                "price": order.price or "",
                "stop_price": order.stop_price or "",
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else "",
                "filled_at": order.filled_at.isoformat() if order.filled_at else "",
                "filled_price": order.filled_price or "",
                "filled_quantity": order.filled_quantity or "",
                "etoro_order_id": order.etoro_order_id or ""
            })
        
        return self._export_csv(data, output_file or "orders.csv")

    def _export_positions_json(
        self,
        positions: List[PositionORM],
        output_file: Optional[str]
    ) -> Path:
        """Export positions to JSON."""
        data = []
        for position in positions:
            data.append({
                "id": position.id,
                "strategy_id": position.strategy_id,
                "symbol": position.symbol,
                "side": position.side.value,
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "current_price": position.current_price,
                "unrealized_pnl": position.unrealized_pnl,
                "realized_pnl": position.realized_pnl,
                "opened_at": position.opened_at.isoformat(),
                "closed_at": position.closed_at.isoformat() if position.closed_at else None,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "etoro_position_id": position.etoro_position_id
            })
        
        return self._export_json(data, output_file or "positions.json")

    def _export_positions_csv(
        self,
        positions: List[PositionORM],
        output_file: Optional[str]
    ) -> Path:
        """Export positions to CSV."""
        data = []
        for position in positions:
            data.append({
                "id": position.id,
                "strategy_id": position.strategy_id,
                "symbol": position.symbol,
                "side": position.side.value,
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "current_price": position.current_price,
                "unrealized_pnl": position.unrealized_pnl,
                "realized_pnl": position.realized_pnl,
                "opened_at": position.opened_at.isoformat(),
                "closed_at": position.closed_at.isoformat() if position.closed_at else "",
                "stop_loss": position.stop_loss or "",
                "take_profit": position.take_profit or "",
                "etoro_position_id": position.etoro_position_id
            })
        
        return self._export_csv(data, output_file or "positions.csv")

    def _export_json(self, data: List[Dict[str, Any]], filename: str) -> Path:
        """Export data to JSON file.
        
        Args:
            data: List of dictionaries to export
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        output_path = self.export_dir / filename
        
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(data)} records to {output_path}")
        return output_path

    def _export_csv(self, data: List[Dict[str, Any]], filename: str) -> Path:
        """Export data to CSV file.
        
        Args:
            data: List of dictionaries to export
            filename: Output filename
            
        Returns:
            Path to exported file
        """
        if not data:
            logger.warning(f"No data to export to {filename}")
            output_path = self.export_dir / filename
            output_path.touch()
            return output_path
        
        output_path = self.export_dir / filename
        
        # Get all unique keys from all dictionaries
        fieldnames = set()
        for row in data:
            fieldnames.update(row.keys())
        fieldnames = sorted(fieldnames)
        
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        logger.info(f"Exported {len(data)} records to {output_path}")
        return output_path


class DataExportError(Exception):
    """Data export errors."""
    pass
