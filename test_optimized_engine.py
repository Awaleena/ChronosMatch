"""
Unit Tests for Zero-Copy Optimized Matching Engine
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.order import Order, OrderSide, OrderType, OrderStatus, reset_sequence_counter
from app.matching.engine_optimized import OptimizedMatchingEngine


@pytest.fixture(autouse=True)
def reset_seq():
    reset_sequence_counter()


@pytest.fixture
def opt_engine():
    return OptimizedMatchingEngine("AAPL")


class TestOptimizedEngine:
    def test_full_fill_exact_match(self, opt_engine):
        ask = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 100, 150.0)
        opt_engine.process_order(ask)
        assert opt_engine.total_orders == 1
        assert opt_engine.get_best_ask() == 150.0

        bid = Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 150.0)
        updated_bid, trades = opt_engine.process_order(bid)

        assert updated_bid.status == OrderStatus.FILLED
        assert ask.status == OrderStatus.FILLED
        assert len(trades) == 1
        assert trades[0].quantity == 100
        assert trades[0].execution_price == 150.0
        assert opt_engine.total_orders == 0

    def test_partial_fill_price_time_priority(self, opt_engine):
        s1 = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0)
        s2 = Order("S2", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0)
        opt_engine.process_order(s1)
        opt_engine.process_order(s2)

        bid = Order("B1", "T3", "AAPL", OrderSide.BUY, OrderType.LIMIT, 60, 100.0)
        _, trades = opt_engine.process_order(bid)

        assert len(trades) == 2
        assert trades[0].sell_order_id == "S1"
        assert trades[0].quantity == 50
        assert trades[1].sell_order_id == "S2"
        assert trades[1].quantity == 10
        assert s2.remaining_quantity == 40
        assert opt_engine.total_orders == 1

    def test_maker_price_priority(self, opt_engine):
        # Resting ask @ 100
        opt_engine.process_order(Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0))
        # Aggressive bid @ 105 -> trade at 100.0
        _, trades = opt_engine.process_order(Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 105.0))
        assert trades[0].execution_price == 100.0

    def test_market_order_execution(self, opt_engine):
        opt_engine.process_order(Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 30, 100.0))
        mb = Order("MB1", "T2", "AAPL", OrderSide.BUY, OrderType.MARKET, 50)
        updated, trades = opt_engine.process_order(mb)

        assert len(trades) == 1
        assert trades[0].quantity == 30
        assert updated.filled_quantity == 30
        assert updated.status == OrderStatus.PARTIALLY_FILLED
        assert opt_engine.total_orders == 0

    def test_cancellation(self, opt_engine):
        opt_engine.process_order(Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 95.0))
        assert opt_engine.total_orders == 1

        cancelled = opt_engine.cancel_order("B1")
        assert cancelled.status == OrderStatus.CANCELLED
        assert opt_engine.total_orders == 0
