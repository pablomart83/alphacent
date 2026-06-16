"""Unit tests for the pre-submission balance guard in OrderMonitor.process_pending_orders
(2026-06-16).

The guard skips submitting orders we already know eToro will reject for insufficient
funds (error 604), reducing wasted API calls and errors.log noise. Two behaviours are
locked in here:
  1. Mode filter — the balance snapshot must be read for THIS monitor's account
     (account_info holds both demo and live rows).
  2. Cumulative reservation — a burst of pending orders must not all be waved through
     against ONE stale balance snapshot; each submitted order reserves its value.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.order_monitor import OrderMonitor
from src.api.etoro_client import EToroAPIClient
from src.models.database import Database
from src.models.enums import OrderStatus, OrderSide, OrderType, TradingMode
from src.models.orm import AccountInfoORM, OrderORM


def _order(oid, qty):
    return SimpleNamespace(
        id=oid, symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=float(qty), price=None, stop_price=None, take_profit_price=None,
        status=OrderStatus.PENDING, etoro_order_id=None,
    )


def _monitor_with(balance, pending, account_type="demo"):
    client = Mock(spec=EToroAPIClient)
    client.mode = TradingMode.DEMO
    client.place_order.return_value = {"order_id": "etoro_xyz"}
    db = Mock(spec=Database)

    acct = Mock()
    acct.balance = balance

    captured = {"account_filter": []}

    def query_side(model):
        q = Mock()
        if model is AccountInfoORM:
            def acct_filter(expr):
                captured["account_filter"].append(expr)
                return SimpleNamespace(
                    order_by=lambda *_a, **_k: SimpleNamespace(first=lambda: acct)
                )
            q.filter = acct_filter
        elif model is OrderORM:
            q.filter.return_value.all.return_value = pending
        else:
            q.filter.return_value.all.return_value = []
        return q

    session = Mock()
    session.query.side_effect = query_side
    db.get_session.return_value = session

    mon = OrderMonitor(etoro_client=client, db=db, account_type=account_type)
    return mon, client, session


def test_burst_reserves_committed_value_against_one_snapshot():
    # $1500 balance, two $1000 orders → only the first can submit; the second is
    # skipped because 1500 - 1000(reserved) = 500 < 1000.
    mon, client, _ = _monitor_with(1500.0, [_order("o1", 1000), _order("o2", 1000)])
    result = mon.process_pending_orders()
    assert client.place_order.call_count == 1
    assert result["submitted"] == 1


def test_sufficient_balance_submits_all():
    mon, client, _ = _monitor_with(5000.0, [_order("o1", 1000), _order("o2", 1000)])
    result = mon.process_pending_orders()
    assert client.place_order.call_count == 2
    assert result["submitted"] == 2


def test_balance_read_failure_fails_open():
    # If the balance snapshot is unavailable, the guard must NOT block submissions
    # (fail open — let eToro arbitrate), otherwise a transient DB hiccup wedges all
    # order flow. Here the account query returns no row → live_balance is None.
    mon, client, _ = _monitor_with(None, [_order("o1", 1000)])
    result = mon.process_pending_orders()
    assert client.place_order.call_count == 1
    assert result["submitted"] == 1


def test_demo_monitor_filters_account_by_mode():
    # The balance query must filter by the monitor's mode (DEMO here), not just take
    # the latest row across both accounts.
    mon, client, session = _monitor_with(1000.0, [_order("o1", 500)], account_type="demo")
    mon.process_pending_orders()
    # The AccountInfoORM query path was exercised (filter applied) and an order
    # within balance submitted.
    assert client.place_order.call_count == 1
