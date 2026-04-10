"""Tests for data exporter."""

import csv
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.data.data_exporter import DataExporter
from src.models import (
    OrderORM,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionORM,
    PositionSide,
    StrategyORM,
    StrategyStatus,
)
from src.models.database import Database


@pytest.fixture
def temp_export_dir():
    """Create temporary export directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def database():
    """Create in-memory database for testing."""
    db = Database(":memory:")
    db.initialize()
    return db


@pytest.fixture
def data_exporter(database, temp_export_dir):
    """Create data exporter."""
    return DataExporter(database=database, export_dir=temp_export_dir)


@pytest.fixture
def sample_data(database):
    """Create sample data in database."""
    session = database.get_session()
    
    # Create strategies
    strategy1 = StrategyORM(
        id="strategy_1",
        name="Test Strategy 1",
        description="Test description",
        status=StrategyStatus.LIVE,
        rules={"rule": "value"},
        symbols=["AAPL", "GOOGL"],
        risk_params={"max_loss": 0.03},
        created_at=datetime.now(),
        performance={"total_return": 0.15, "sharpe_ratio": 1.5}
    )
    
    strategy2 = StrategyORM(
        id="strategy_2",
        name="Test Strategy 2",
        description="Another test",
        status=StrategyStatus.DEMO,
        rules={"rule": "value2"},
        symbols=["BTC"],
        risk_params={"max_loss": 0.05},
        created_at=datetime.now(),
        performance={"total_return": 0.25, "sharpe_ratio": 2.0}
    )
    
    session.add(strategy1)
    session.add(strategy2)
    
    # Create orders
    order1 = OrderORM(
        id="order_1",
        strategy_id="strategy_1",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.FILLED,
        filled_price=150.0,
        filled_quantity=10.0
    )
    
    order2 = OrderORM(
        id="order_2",
        strategy_id="strategy_2",
        symbol="BTC",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.5,
        status=OrderStatus.PENDING,
        price=50000.0
    )
    
    session.add(order1)
    session.add(order2)
    
    # Create positions
    position1 = PositionORM(
        id="position_1",
        strategy_id="strategy_1",
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=10.0,
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=50.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos_1"
    )
    
    position2 = PositionORM(
        id="position_2",
        strategy_id="strategy_2",
        symbol="BTC",
        side=PositionSide.LONG,
        quantity=0.5,
        entry_price=50000.0,
        current_price=51000.0,
        unrealized_pnl=500.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos_2",
        closed_at=datetime.now()
    )
    
    session.add(position1)
    session.add(position2)
    
    session.commit()
    session.close()


def test_export_strategies_json(data_exporter, sample_data):
    """Test exporting strategies to JSON."""
    output_path = data_exporter.export_strategies(format="json")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 2
    assert data[0]["name"] == "Test Strategy 1"
    assert data[1]["name"] == "Test Strategy 2"


def test_export_strategies_csv(data_exporter, sample_data):
    """Test exporting strategies to CSV."""
    output_path = data_exporter.export_strategies(format="csv")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    assert len(rows) == 2
    assert rows[0]["name"] == "Test Strategy 1"


def test_export_orders_json(data_exporter, sample_data):
    """Test exporting orders to JSON."""
    output_path = data_exporter.export_orders(format="json")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 2
    assert data[0]["symbol"] == "AAPL"
    assert data[1]["symbol"] == "BTC"


def test_export_orders_csv(data_exporter, sample_data):
    """Test exporting orders to CSV."""
    output_path = data_exporter.export_orders(format="csv")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    assert len(rows) == 2


def test_export_orders_filtered_by_strategy(data_exporter, sample_data):
    """Test exporting orders filtered by strategy."""
    output_path = data_exporter.export_orders(
        format="json",
        strategy_id="strategy_1"
    )
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 1
    assert data[0]["strategy_id"] == "strategy_1"


def test_export_positions_json(data_exporter, sample_data):
    """Test exporting positions to JSON."""
    output_path = data_exporter.export_positions(format="json")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 2


def test_export_positions_csv(data_exporter, sample_data):
    """Test exporting positions to CSV."""
    output_path = data_exporter.export_positions(format="csv")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    assert len(rows) == 2


def test_export_positions_exclude_closed(data_exporter, sample_data):
    """Test exporting only open positions."""
    output_path = data_exporter.export_positions(
        format="json",
        include_closed=False
    )
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    # Only position_1 should be included (position_2 is closed)
    assert len(data) == 1
    assert data[0]["id"] == "position_1"


def test_export_performance_metrics_json(data_exporter, sample_data):
    """Test exporting performance metrics to JSON."""
    output_path = data_exporter.export_performance_metrics(format="json")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 2
    assert "total_return" in data[0]
    assert "sharpe_ratio" in data[0]


def test_export_performance_metrics_csv(data_exporter, sample_data):
    """Test exporting performance metrics to CSV."""
    output_path = data_exporter.export_performance_metrics(format="csv")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    assert len(rows) == 2


def test_export_all_json(data_exporter, sample_data):
    """Test exporting all data to JSON."""
    exports = data_exporter.export_all(format="json")
    
    assert "strategies" in exports
    assert "orders" in exports
    assert "positions" in exports
    assert "performance" in exports
    
    # Verify all files exist
    for path in exports.values():
        assert path.exists()


def test_export_all_csv(data_exporter, sample_data):
    """Test exporting all data to CSV."""
    exports = data_exporter.export_all(format="csv")
    
    assert "strategies" in exports
    assert "orders" in exports
    assert "positions" in exports
    assert "performance" in exports
    
    # Verify all files exist
    for path in exports.values():
        assert path.exists()


def test_export_custom_filename(data_exporter, sample_data):
    """Test exporting with custom filename."""
    output_path = data_exporter.export_strategies(
        format="json",
        output_file="custom_strategies.json"
    )
    
    assert output_path.name == "custom_strategies.json"
    assert output_path.exists()


def test_export_empty_data(data_exporter):
    """Test exporting when no data exists."""
    output_path = data_exporter.export_strategies(format="json")
    
    assert output_path.exists()
    
    with open(output_path, "r") as f:
        data = json.load(f)
    
    assert len(data) == 0


def test_export_unsupported_format(data_exporter, sample_data):
    """Test exporting with unsupported format."""
    with pytest.raises(ValueError):
        data_exporter.export_strategies(format="xml")
