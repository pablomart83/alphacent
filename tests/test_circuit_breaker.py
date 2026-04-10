"""Tests for eToro API circuit breaker."""

import time
import pytest
from unittest.mock import patch

from src.api.etoro_client import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitBreakerState,
    EToroAPIClient,
    EToroAPIError,
)
from src.models import TradingMode


class TestCircuitBreaker:
    """Unit tests for the CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("orders")
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.allow_request() is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker("orders", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.allow_request() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("orders", failure_threshold=5)
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("orders", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        cb.record_success()
        # After success, counter resets — 4 more failures should not open
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_transitions_to_half_open_after_cooldown(self):
        cb = CircuitBreaker("orders", failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitBreakerState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker("orders", failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb._consecutive_failures == 0

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker("orders", failure_threshold=2, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.allow_request() is False

    def test_get_state_info_returns_dict(self):
        cb = CircuitBreaker("market_data", failure_threshold=3, cooldown_seconds=30)
        info = cb.get_state_info()
        assert info["category"] == "market_data"
        assert info["state"] == "closed"
        assert info["consecutive_failures"] == 0
        assert info["failure_threshold"] == 3
        assert info["cooldown_seconds"] == 30

    def test_get_state_info_when_open(self):
        cb = CircuitBreaker("positions", failure_threshold=2, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        info = cb.get_state_info()
        assert info["state"] == "open"
        assert info["consecutive_failures"] == 2
        assert info["opened_at"] is not None


class TestEToroClientCircuitBreaker:
    """Tests for circuit breaker integration in EToroAPIClient."""

    def _make_client(self):
        return EToroAPIClient(
            public_key="test_pub",
            user_key="test_usr",
            mode=TradingMode.DEMO,
        )

    def test_client_has_circuit_breakers(self):
        client = self._make_client()
        assert "orders" in client._circuit_breakers
        assert "positions" in client._circuit_breakers
        assert "market_data" in client._circuit_breakers

    def test_get_circuit_breaker_states(self):
        client = self._make_client()
        states = client.get_circuit_breaker_states()
        assert len(states) == 3
        for name in ("orders", "positions", "market_data"):
            assert states[name]["state"] == "closed"

    def test_orders_circuit_breaker_rejects_place_order(self):
        client = self._make_client()
        cb = client._circuit_breakers["orders"]
        # Force open
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        from src.models import OrderSide, OrderType
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            client.place_order(
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=100,
            )
        assert exc_info.value.category == "orders"

    def test_orders_circuit_breaker_rejects_cancel_order(self):
        client = self._make_client()
        cb = client._circuit_breakers["orders"]
        for _ in range(5):
            cb.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            client.cancel_order("12345")

    def test_positions_circuit_breaker_returns_cached_positions(self):
        client = self._make_client()
        # Seed the cache
        from src.models import Position, PositionSide
        from datetime import datetime
        cached = [
            Position(
                id="p1", strategy_id="s1", symbol="AAPL",
                side=PositionSide.LONG, quantity=10, entry_price=150.0,
                current_price=155.0, unrealized_pnl=50.0, realized_pnl=0.0,
                opened_at=datetime.now(), etoro_position_id="p1",
            )
        ]
        client._cached_positions = cached

        # Force open the positions circuit breaker
        cb = client._circuit_breakers["positions"]
        for _ in range(5):
            cb.record_failure()

        result = client.get_positions()
        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    def test_positions_circuit_breaker_raises_without_cache(self):
        client = self._make_client()
        client._cached_positions = None

        cb = client._circuit_breakers["positions"]
        for _ in range(5):
            cb.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            client.get_positions()

    def test_market_data_circuit_breaker_returns_cached(self):
        client = self._make_client()
        from src.models import MarketData, DataSource
        from datetime import datetime
        cached_md = MarketData(
            symbol="AAPL", timestamp=datetime.now(),
            open=150.0, high=155.0, low=149.0, close=153.0,
            volume=1000.0, source=DataSource.ETORO,
        )
        client._cached_market_data["AAPL"] = cached_md

        cb = client._circuit_breakers["market_data"]
        for _ in range(5):
            cb.record_failure()

        result = client.get_market_data("AAPL")
        assert result.symbol == "AAPL"
        assert result.close == 153.0

    def test_market_data_circuit_breaker_raises_without_cache(self):
        client = self._make_client()
        cb = client._circuit_breakers["market_data"]
        for _ in range(5):
            cb.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            client.get_market_data("MSFT")

    def test_close_position_rejects_when_circuit_open(self):
        client = self._make_client()
        cb = client._circuit_breakers["positions"]
        for _ in range(5):
            cb.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            client.close_position("pos123")

    def test_update_stop_loss_rejects_when_circuit_open(self):
        client = self._make_client()
        cb = client._circuit_breakers["positions"]
        for _ in range(5):
            cb.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            client.update_position_stop_loss("pos123", 145.0)

    def test_category_mapping(self):
        client = self._make_client()
        assert client._get_category_for_method("place_order") == "orders"
        assert client._get_category_for_method("get_positions") == "positions"
        assert client._get_category_for_method("get_market_data") == "market_data"
        assert client._get_category_for_method("unknown_method") == ""
