"""Tests for transaction logger."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.data.transaction_logger import TransactionLogger
from src.models import Order, OrderSide, OrderStatus, OrderType


@pytest.fixture
def temp_log_dir():
    """Create temporary log directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def transaction_logger(temp_log_dir):
    """Create transaction logger with temp directory."""
    return TransactionLogger(log_dir=temp_log_dir, max_log_size_mb=1, max_archive_count=3)


@pytest.fixture
def sample_order():
    """Create sample order for testing."""
    return Order(
        id="order_123",
        strategy_id="strategy_456",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        etoro_order_id="etoro_789"
    )


def test_log_order_submitted(transaction_logger, sample_order, temp_log_dir):
    """Test logging order submission."""
    transaction_logger.log_order_submitted(sample_order)
    
    # Verify log file created
    log_file = Path(temp_log_dir) / "transactions.jsonl"
    assert log_file.exists()
    
    # Verify log entry
    with open(log_file, "r") as f:
        entry = json.loads(f.readline())
    
    assert entry["event_type"] == "order_submitted"
    assert entry["order_id"] == "order_123"
    assert entry["strategy_id"] == "strategy_456"
    assert entry["symbol"] == "AAPL"
    assert entry["side"] == "BUY"
    assert entry["order_type"] == "MARKET"
    assert entry["quantity"] == 10.0
    assert entry["etoro_order_id"] == "etoro_789"
    assert "timestamp" in entry


def test_log_order_filled(transaction_logger, sample_order):
    """Test logging order fill."""
    fill_time = datetime.now()
    transaction_logger.log_order_filled(
        sample_order,
        filled_price=150.0,
        filled_quantity=10.0,
        fill_timestamp=fill_time
    )
    
    # Retrieve and verify
    transactions = transaction_logger.get_transactions(order_id="order_123")
    assert len(transactions) == 1
    
    entry = transactions[0]
    assert entry["event_type"] == "order_filled"
    assert entry["filled_price"] == 150.0
    assert entry["filled_quantity"] == 10.0


def test_log_order_cancelled(transaction_logger, sample_order):
    """Test logging order cancellation."""
    transaction_logger.log_order_cancelled(sample_order, reason="User requested")
    
    transactions = transaction_logger.get_transactions(order_id="order_123")
    assert len(transactions) == 1
    
    entry = transactions[0]
    assert entry["event_type"] == "order_cancelled"
    assert entry["reason"] == "User requested"


def test_log_order_failed(transaction_logger, sample_order):
    """Test logging order failure."""
    transaction_logger.log_order_failed(sample_order, error="Insufficient funds")
    
    transactions = transaction_logger.get_transactions(order_id="order_123")
    assert len(transactions) == 1
    
    entry = transactions[0]
    assert entry["event_type"] == "order_failed"
    assert entry["error"] == "Insufficient funds"


def test_log_partial_fill(transaction_logger, sample_order):
    """Test logging partial fill."""
    fill_time = datetime.now()
    transaction_logger.log_partial_fill(
        sample_order,
        filled_price=150.0,
        filled_quantity=5.0,
        remaining_quantity=5.0,
        fill_timestamp=fill_time
    )
    
    transactions = transaction_logger.get_transactions(order_id="order_123")
    assert len(transactions) == 1
    
    entry = transactions[0]
    assert entry["event_type"] == "order_partial_fill"
    assert entry["filled_quantity"] == 5.0
    assert entry["remaining_quantity"] == 5.0


def test_log_rotation(temp_log_dir):
    """Test log rotation when size limit exceeded."""
    # Create logger with very small max size
    logger = TransactionLogger(log_dir=temp_log_dir, max_log_size_mb=0.001, max_archive_count=3)
    
    order = Order(
        id="order_123",
        strategy_id="strategy_456",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING
    )
    
    # Log many entries to trigger rotation
    for i in range(100):
        logger.log_order_submitted(order)
    
    # Check that archives were created
    log_dir = Path(temp_log_dir)
    archives = list(log_dir.glob("transactions_*.jsonl"))
    assert len(archives) > 0


def test_archive_cleanup(temp_log_dir):
    """Test cleanup of old archives."""
    logger = TransactionLogger(log_dir=temp_log_dir, max_log_size_mb=0.001, max_archive_count=2)
    
    order = Order(
        id="order_123",
        strategy_id="strategy_456",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING
    )
    
    # Log many entries to trigger multiple rotations
    for i in range(500):
        logger.log_order_submitted(order)
    
    # Check that only max_archive_count archives are kept
    log_dir = Path(temp_log_dir)
    archives = list(log_dir.glob("transactions_*.jsonl"))
    assert len(archives) <= 2


def test_get_transactions_by_strategy(transaction_logger):
    """Test filtering transactions by strategy ID."""
    order1 = Order(
        id="order_1",
        strategy_id="strategy_A",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING
    )
    
    order2 = Order(
        id="order_2",
        strategy_id="strategy_B",
        symbol="GOOGL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5.0,
        status=OrderStatus.PENDING
    )
    
    transaction_logger.log_order_submitted(order1)
    transaction_logger.log_order_submitted(order2)
    
    # Filter by strategy A
    transactions = transaction_logger.get_transactions(strategy_id="strategy_A")
    assert len(transactions) == 1
    assert transactions[0]["order_id"] == "order_1"


def test_get_transactions_by_time_range(transaction_logger, sample_order):
    """Test filtering transactions by time range."""
    start_time = datetime.now()
    
    transaction_logger.log_order_submitted(sample_order)
    
    end_time = datetime.now()
    
    # Should find transaction within range
    transactions = transaction_logger.get_transactions(
        start_time=start_time,
        end_time=end_time
    )
    assert len(transactions) == 1
