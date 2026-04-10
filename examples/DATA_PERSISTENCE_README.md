# Data Persistence and Recovery

This document describes the data persistence and recovery features implemented in AlphaCent.

## Overview

The data persistence and recovery system provides comprehensive functionality for:

1. **Transaction Logging** - Audit trail of all orders and fills
2. **Automatic Backups** - Scheduled backups with rotation
3. **State Restoration** - Recovery from backups with fallback handling
4. **Data Export** - Export data to CSV and JSON formats

## Components

### 1. Transaction Logger

Logs all order and fill transactions with automatic rotation and archival.

**Features:**
- Logs order submissions, fills, cancellations, failures, and partial fills
- Automatic log rotation when size limit exceeded
- Archive cleanup (keeps last N archives)
- Query transactions by order ID, strategy ID, or time range

**Usage:**
```python
from src.data import TransactionLogger
from src.models import Order, OrderSide, OrderType, OrderStatus

# Create logger
tx_logger = TransactionLogger(
    log_dir="logs/transactions",
    max_log_size_mb=10,
    max_archive_count=5
)

# Log order submission
order = Order(
    id="order_123",
    strategy_id="strategy_456",
    symbol="AAPL",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=10.0,
    status=OrderStatus.PENDING
)
tx_logger.log_order_submitted(order)

# Log order fill
tx_logger.log_order_filled(
    order,
    filled_price=150.0,
    filled_quantity=10.0,
    fill_timestamp=datetime.now()
)

# Query transactions
transactions = tx_logger.get_transactions(order_id="order_123")
```

**Log Format:**
Transaction logs are stored as JSON Lines (`.jsonl`) with one transaction per line:
```json
{
  "event_type": "order_submitted",
  "timestamp": "2026-02-14T10:35:02.191895",
  "order_id": "order_123",
  "strategy_id": "strategy_456",
  "symbol": "AAPL",
  "side": "BUY",
  "order_type": "MARKET",
  "quantity": 10.0,
  "etoro_order_id": "etoro_789"
}
```

### 2. Backup Manager

Creates and manages automatic backups of critical data with rotation.

**Features:**
- Backup database, configuration, and optionally logs
- Automatic backup rotation (keeps last N backups)
- Backup verification and integrity checking
- Scheduled backups at regular intervals

**Usage:**
```python
from src.data import BackupManager, BackupScheduler

# Create backup manager
backup_manager = BackupManager(
    backup_dir="backups",
    max_backups=10
)

# Create manual backup
backup_path = backup_manager.create_backup(
    db_path="alphacent.db",
    config_dir="config",
    include_logs=False
)

# List all backups
backups = backup_manager.list_backups()

# Get latest backup
latest = backup_manager.get_latest_backup()

# Verify backup integrity
is_valid = backup_manager.verify_backup(latest)

# Set up scheduled backups
scheduler = BackupScheduler(
    backup_manager=backup_manager,
    interval_hours=24
)

# Run backup if due
scheduler.run_backup()
```

**Backup Structure:**
```
backups/
├── backup_20260214_103910_195937/
│   ├── alphacent.db
│   ├── config/
│   │   ├── app_config.json
│   │   ├── risk_config.json
│   │   └── ...
│   ├── logs/ (optional)
│   │   └── ...
│   └── backup_metadata.json
└── backup_20260214_104520_123456/
    └── ...
```

### 3. State Manager

Manages state restoration from backups with fallback handling.

**Features:**
- Restore from latest or specific backup
- Automatic fallback to older backups if latest is corrupted
- Restore on startup with default state initialization
- Selective restoration (database, config, logs)

**Usage:**
```python
from src.data import BackupManager, StateManager

# Create managers
backup_manager = BackupManager(backup_dir="backups")
state_manager = StateManager(
    backup_manager=backup_manager,
    db_path="alphacent.db",
    config_dir="config"
)

# Restore on startup (automatic)
result = state_manager.restore_on_startup(
    restore_config=True,
    restore_logs=False
)

# Manual restoration from latest backup
result = state_manager.restore_from_backup()

# Manual restoration from specific backup
result = state_manager.restore_from_backup(
    backup_path=Path("backups/backup_20260214_103910_195937")
)
```

**Restoration Process:**
1. Verify backup integrity
2. If verification fails, try fallback to older backups
3. If all backups fail, initialize with default state
4. Backup current files before overwriting
5. Restore database, configuration, and optionally logs

### 4. Data Exporter

Exports data to CSV and JSON formats for external analysis.

**Features:**
- Export strategies, orders, positions, performance metrics
- Support for JSON and CSV formats
- Filter exports by strategy ID or other criteria
- Export all data at once with timestamped filenames

**Usage:**
```python
from src.data import DataExporter
from src.models.database import get_database

# Create exporter
db = get_database("alphacent.db")
exporter = DataExporter(
    database=db,
    export_dir="exports"
)

# Export strategies to JSON
strategies_path = exporter.export_strategies(format="json")

# Export orders to CSV
orders_path = exporter.export_orders(format="csv")

# Export orders for specific strategy
orders_path = exporter.export_orders(
    format="json",
    strategy_id="strategy_123"
)

# Export positions (exclude closed)
positions_path = exporter.export_positions(
    format="json",
    include_closed=False
)

# Export performance metrics
performance_path = exporter.export_performance_metrics(format="json")

# Export all data at once
exports = exporter.export_all(format="json")
# Returns: {
#   "strategies": Path("exports/strategies_20260214_103910.json"),
#   "orders": Path("exports/orders_20260214_103910.json"),
#   "positions": Path("exports/positions_20260214_103910.json"),
#   "performance": Path("exports/performance_20260214_103910.json")
# }
```

**Export Formats:**

JSON format preserves all data types and nested structures:
```json
[
  {
    "id": "strategy_1",
    "name": "Momentum Strategy",
    "status": "LIVE",
    "symbols": ["AAPL", "GOOGL"],
    "performance": {
      "total_return": 0.15,
      "sharpe_ratio": 1.5
    }
  }
]
```

CSV format flattens nested structures:
```csv
id,name,status,symbols,perf_total_return,perf_sharpe_ratio
strategy_1,Momentum Strategy,LIVE,"AAPL,GOOGL",0.15,1.5
```

## Integration with AlphaCent

### Startup Sequence

```python
from src.data import BackupManager, StateManager
from src.models.database import get_database

# 1. Initialize backup manager
backup_manager = BackupManager(backup_dir="backups", max_backups=10)

# 2. Initialize state manager
state_manager = StateManager(
    backup_manager=backup_manager,
    db_path="alphacent.db",
    config_dir="config"
)

# 3. Restore state on startup
state_manager.restore_on_startup(restore_config=True)

# 4. Initialize database
db = get_database("alphacent.db")

# 5. Set up scheduled backups
from src.data import BackupScheduler
scheduler = BackupScheduler(backup_manager, interval_hours=24)
```

### Order Execution Integration

```python
from src.data import TransactionLogger

# Initialize transaction logger
tx_logger = TransactionLogger()

# In OrderExecutor.execute_signal()
def execute_signal(self, signal, position_size):
    order = self._create_order(signal, position_size)
    
    # Log order submission
    tx_logger.log_order_submitted(order)
    
    # Submit to eToro API
    response = self.etoro_client.place_order(order)
    
    # Track order status
    if response.status == "FILLED":
        tx_logger.log_order_filled(
            order,
            filled_price=response.filled_price,
            filled_quantity=response.filled_quantity,
            fill_timestamp=datetime.now()
        )
    elif response.status == "FAILED":
        tx_logger.log_order_failed(order, error=response.error)
    
    return order
```

### Periodic Backup

```python
import threading
import time

def backup_thread(scheduler):
    """Background thread for periodic backups."""
    while True:
        scheduler.run_backup()
        time.sleep(3600)  # Check every hour

# Start backup thread
thread = threading.Thread(
    target=backup_thread,
    args=(scheduler,),
    daemon=True
)
thread.start()
```

## Best Practices

1. **Transaction Logging**
   - Log all order events (submission, fill, cancellation, failure)
   - Use transaction logs for audit trails and debugging
   - Query logs by strategy ID for performance analysis

2. **Backups**
   - Schedule automatic backups at least daily
   - Keep at least 7-10 backups for recovery options
   - Verify backup integrity periodically
   - Include logs in backups for critical systems

3. **State Restoration**
   - Always restore state on startup
   - Test restoration process regularly
   - Keep backup rotation count high enough for recovery window

4. **Data Export**
   - Export data regularly for external analysis
   - Use JSON for complete data preservation
   - Use CSV for spreadsheet analysis
   - Archive exports for historical records

## Error Handling

All components include comprehensive error handling:

- **Transaction Logger**: Continues logging even if individual writes fail
- **Backup Manager**: Validates backups and cleans up corrupted files
- **State Manager**: Falls back to older backups if latest is corrupted
- **Data Exporter**: Handles empty data gracefully

## Testing

Run tests for all components:

```bash
# Test transaction logger
pytest tests/test_transaction_logger.py -v

# Test backup manager
pytest tests/test_backup_manager.py -v

# Test state manager
pytest tests/test_state_manager.py -v

# Test data exporter
pytest tests/test_data_exporter.py -v

# Run all tests
pytest tests/test_transaction_logger.py tests/test_backup_manager.py \
       tests/test_state_manager.py tests/test_data_exporter.py -v
```

## Example

See `examples/data_persistence_example.py` for a complete demonstration of all features.

```bash
python examples/data_persistence_example.py
```

## Requirements Validation

This implementation satisfies the following requirements:

- **Requirement 14.1**: All configuration, strategies, and state persisted to local storage
- **Requirement 14.2**: Automatic backups of critical data at regular intervals
- **Requirement 14.3**: State restoration from most recent backup on startup
- **Requirement 14.4**: Fallback to older backups if restoration fails, default state if all fail
- **Requirement 14.5**: Transaction log of all orders and fills maintained
- **Requirement 14.6**: Manual export of all data for external analysis supported
- **Requirement 14.7**: Data corruption detection and recovery from backup
