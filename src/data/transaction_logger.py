"""Transaction logging for all orders and fills with rotation and archival."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.models import Order, OrderStatus

logger = logging.getLogger(__name__)


class TransactionLogger:
    """Logs all order and fill transactions with automatic rotation."""

    def __init__(
        self,
        log_dir: str = "logs/transactions",
        max_log_size_mb: int = 10,
        max_archive_count: int = 10
    ):
        """Initialize transaction logger.
        
        Args:
            log_dir: Directory for transaction logs
            max_log_size_mb: Maximum log file size before rotation (MB)
            max_archive_count: Maximum number of archived logs to keep
        """
        self.log_dir = Path(log_dir)
        # Ensure the directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_log_size_bytes = max_log_size_mb * 1024 * 1024
        self.max_archive_count = max_archive_count
        
        self.current_log_file = self.log_dir / "transactions.jsonl"
        
        logger.info(f"Transaction logger initialized at {self.log_dir}")

    def log_order_submitted(self, order: Order) -> None:
        """Log order submission event.
        
        Args:
            order: Order that was submitted
        """
        entry = {
            "event_type": "order_submitted",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "price": order.price,
            "stop_price": order.stop_price,
            "etoro_order_id": order.etoro_order_id
        }
        self._write_entry(entry)
        logger.debug(f"Logged order submission: {order.id}")

    def log_order_filled(
        self,
        order: Order,
        filled_price: float,
        filled_quantity: float,
        fill_timestamp: datetime
    ) -> None:
        """Log order fill event.
        
        Args:
            order: Order that was filled
            filled_price: Price at which order was filled
            filled_quantity: Quantity that was filled
            fill_timestamp: Timestamp of fill
        """
        entry = {
            "event_type": "order_filled",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "filled_price": filled_price,
            "filled_quantity": filled_quantity,
            "fill_timestamp": fill_timestamp.isoformat(),
            "etoro_order_id": order.etoro_order_id
        }
        self._write_entry(entry)
        logger.debug(f"Logged order fill: {order.id}")

    def log_order_cancelled(self, order: Order, reason: str = "") -> None:
        """Log order cancellation event.
        
        Args:
            order: Order that was cancelled
            reason: Reason for cancellation
        """
        entry = {
            "event_type": "order_cancelled",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "reason": reason,
            "etoro_order_id": order.etoro_order_id
        }
        self._write_entry(entry)
        logger.debug(f"Logged order cancellation: {order.id}")

    def log_order_failed(self, order: Order, error: str) -> None:
        """Log order failure event.
        
        Args:
            order: Order that failed
            error: Error message
        """
        entry = {
            "event_type": "order_failed",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "error": error,
            "etoro_order_id": order.etoro_order_id
        }
        self._write_entry(entry)
        logger.debug(f"Logged order failure: {order.id}")

    def log_partial_fill(
        self,
        order: Order,
        filled_price: float,
        filled_quantity: float,
        remaining_quantity: float,
        fill_timestamp: datetime
    ) -> None:
        """Log partial fill event.
        
        Args:
            order: Order that was partially filled
            filled_price: Price at which partial fill occurred
            filled_quantity: Quantity that was filled
            remaining_quantity: Quantity still remaining
            fill_timestamp: Timestamp of partial fill
        """
        entry = {
            "event_type": "order_partial_fill",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "filled_price": filled_price,
            "filled_quantity": filled_quantity,
            "remaining_quantity": remaining_quantity,
            "fill_timestamp": fill_timestamp.isoformat(),
            "etoro_order_id": order.etoro_order_id
        }
        self._write_entry(entry)
        logger.debug(f"Logged partial fill: {order.id}")

    def _write_entry(self, entry: Dict[str, Any]) -> None:
        """Write transaction entry to log file.
        
        Args:
            entry: Transaction entry dictionary
        """
        # Check if rotation needed
        if self.current_log_file.exists():
            file_size = self.current_log_file.stat().st_size
            if file_size >= self.max_log_size_bytes:
                self._rotate_log()
        
        # Write entry as JSON line
        with open(self.current_log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _rotate_log(self) -> None:
        """Rotate current log file and archive it."""
        if not self.current_log_file.exists():
            return
        
        # Create archive filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = self.log_dir / f"transactions_{timestamp}.jsonl"
        
        # Move current log to archive
        self.current_log_file.rename(archive_file)
        logger.info(f"Rotated transaction log to {archive_file}")
        
        # Clean up old archives
        self._cleanup_archives()

    def _cleanup_archives(self) -> None:
        """Remove old archived logs beyond max_archive_count."""
        # Get all archived log files
        archives = sorted(
            self.log_dir.glob("transactions_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Remove old archives
        for archive in archives[self.max_archive_count:]:
            archive.unlink()
            logger.info(f"Removed old transaction log archive: {archive}")

    def get_transactions(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        order_id: Optional[str] = None,
        strategy_id: Optional[str] = None
    ) -> list:
        """Retrieve transactions matching filters.
        
        Args:
            start_time: Filter transactions after this time
            end_time: Filter transactions before this time
            order_id: Filter by specific order ID
            strategy_id: Filter by specific strategy ID
            
        Returns:
            List of transaction entries
        """
        transactions = []
        
        # Read from current log
        if self.current_log_file.exists():
            transactions.extend(self._read_log_file(self.current_log_file))
        
        # Read from archives
        for archive in self.log_dir.glob("transactions_*.jsonl"):
            transactions.extend(self._read_log_file(archive))
        
        # Apply filters
        filtered = transactions
        
        if start_time:
            filtered = [
                t for t in filtered
                if datetime.fromisoformat(t["timestamp"]) >= start_time
            ]
        
        if end_time:
            filtered = [
                t for t in filtered
                if datetime.fromisoformat(t["timestamp"]) <= end_time
            ]
        
        if order_id:
            filtered = [t for t in filtered if t.get("order_id") == order_id]
        
        if strategy_id:
            filtered = [t for t in filtered if t.get("strategy_id") == strategy_id]
        
        return filtered

    def _read_log_file(self, log_file: Path) -> list:
        """Read transactions from a log file.
        
        Args:
            log_file: Path to log file
            
        Returns:
            List of transaction entries
        """
        transactions = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        transactions.append(json.loads(line))
        except Exception as e:
            logger.error(f"Error reading log file {log_file}: {e}")
        
        return transactions
