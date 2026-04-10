"""Example demonstrating data persistence and recovery features."""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data import (
    BackupManager,
    BackupScheduler,
    DataExporter,
    StateManager,
    TransactionLogger,
)
from src.models import Order, OrderSide, OrderStatus, OrderType
from src.models.database import get_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def demonstrate_transaction_logging():
    """Demonstrate transaction logging functionality."""
    logger.info("=== Transaction Logging Demo ===")
    
    # Create transaction logger
    tx_logger = TransactionLogger(
        log_dir="logs/transactions",
        max_log_size_mb=10,
        max_archive_count=5
    )
    
    # Create sample order
    order = Order(
        id="order_demo_123",
        strategy_id="strategy_momentum",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING
    )
    
    # Log order submission
    tx_logger.log_order_submitted(order)
    logger.info("Logged order submission")
    
    # Simulate order fill
    order.status = OrderStatus.FILLED
    tx_logger.log_order_filled(
        order,
        filled_price=150.0,
        filled_quantity=10.0,
        fill_timestamp=datetime.now()
    )
    logger.info("Logged order fill")
    
    # Retrieve transactions
    transactions = tx_logger.get_transactions(order_id="order_demo_123")
    logger.info(f"Retrieved {len(transactions)} transactions for order")
    
    for tx in transactions:
        logger.info(f"  - {tx['event_type']} at {tx['timestamp']}")


def demonstrate_backup_system():
    """Demonstrate automatic backup system."""
    logger.info("\n=== Backup System Demo ===")
    
    # Create backup manager
    backup_manager = BackupManager(
        backup_dir="backups",
        max_backups=10
    )
    
    # Create a backup
    logger.info("Creating backup...")
    backup_path = backup_manager.create_backup(
        db_path="alphacent.db",
        config_dir="config",
        include_logs=False
    )
    logger.info(f"Backup created at: {backup_path}")
    
    # List all backups
    backups = backup_manager.list_backups()
    logger.info(f"Total backups: {len(backups)}")
    
    for backup in backups[:3]:  # Show first 3
        logger.info(f"  - {backup['timestamp']} at {backup['path']}")
    
    # Verify backup
    latest = backup_manager.get_latest_backup()
    if latest:
        is_valid = backup_manager.verify_backup(latest)
        logger.info(f"Latest backup valid: {is_valid}")
    
    # Demonstrate scheduled backups
    logger.info("\nSetting up backup scheduler...")
    scheduler = BackupScheduler(
        backup_manager=backup_manager,
        interval_hours=24
    )
    
    if scheduler.should_backup():
        logger.info("Backup is due, running scheduled backup...")
        scheduler.run_backup()
    else:
        logger.info("Backup not due yet")


def demonstrate_state_restoration():
    """Demonstrate state restoration from backups."""
    logger.info("\n=== State Restoration Demo ===")
    
    # Create backup manager and state manager
    backup_manager = BackupManager(backup_dir="backups")
    state_manager = StateManager(
        backup_manager=backup_manager,
        db_path="alphacent.db",
        config_dir="config"
    )
    
    # Check if restoration is needed on startup
    logger.info("Checking if state restoration needed...")
    result = state_manager.restore_on_startup(
        restore_config=True,
        restore_logs=False
    )
    
    if result:
        logger.info("State restoration successful or not needed")
    else:
        logger.info("State restoration failed, using default state")
    
    # Demonstrate manual restoration from specific backup
    latest_backup = backup_manager.get_latest_backup()
    if latest_backup:
        logger.info(f"\nManual restoration from: {latest_backup}")
        result = state_manager.restore_from_backup(
            backup_path=latest_backup,
            restore_config=True
        )
        logger.info(f"Manual restoration result: {result}")


def demonstrate_data_export():
    """Demonstrate data export functionality."""
    logger.info("\n=== Data Export Demo ===")
    
    # Initialize database
    db = get_database("alphacent.db")
    
    # Create data exporter
    exporter = DataExporter(
        database=db,
        export_dir="exports"
    )
    
    # Export strategies to JSON
    logger.info("Exporting strategies to JSON...")
    strategies_path = exporter.export_strategies(format="json")
    logger.info(f"Strategies exported to: {strategies_path}")
    
    # Export orders to CSV
    logger.info("Exporting orders to CSV...")
    orders_path = exporter.export_orders(format="csv")
    logger.info(f"Orders exported to: {orders_path}")
    
    # Export positions to JSON
    logger.info("Exporting positions to JSON...")
    positions_path = exporter.export_positions(format="json")
    logger.info(f"Positions exported to: {positions_path}")
    
    # Export performance metrics
    logger.info("Exporting performance metrics...")
    performance_path = exporter.export_performance_metrics(format="json")
    logger.info(f"Performance metrics exported to: {performance_path}")
    
    # Export all data at once
    logger.info("\nExporting all data...")
    exports = exporter.export_all(format="json")
    logger.info("All data exported:")
    for data_type, path in exports.items():
        logger.info(f"  - {data_type}: {path}")


def main():
    """Run all demonstrations."""
    logger.info("AlphaCent Data Persistence and Recovery Demo")
    logger.info("=" * 60)
    
    try:
        # Run demonstrations
        demonstrate_transaction_logging()
        demonstrate_backup_system()
        demonstrate_state_restoration()
        demonstrate_data_export()
        
        logger.info("\n" + "=" * 60)
        logger.info("Demo completed successfully!")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
