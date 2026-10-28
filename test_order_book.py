"""
Comprehensive Unit Tests for High-Performance In-Memory Order Book
"""
import pytest
import threading
import sys
import os

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.order import Order, OrderSide, OrderType, OrderStatus, reset_sequence_counter
from app.matching.order_book import OrderBook
from app.matching.price_level import PriceLevel


@pytest.fixture(autouse=True)
def reset_seq():
    reset_sequence_counter()


@pytest.fixture
def empty_book():
    return OrderBook("AAPL")


class TestPriceLevel:
    def test_price_level_lifecycle(self):
        pl = PriceLevel(150.25)
        assert pl.price == 150.25
        assert pl.is_empty() is True
        assert pl.order_count == 0
        assert pl.total_quantity == 0
        assert pl.peek() is None

        o1 = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 150.25)
        o2 = Order("O2", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 30, 150.25)

        pl.add_order(o1)
        assert pl.is_empty() is False
        assert pl.order_count == 1
        assert pl.total_quantity == 50
        assert pl.peek() == o1

        pl.add_order(o2)
        assert pl.order_count == 2
        assert pl.total_quantity == 80
        assert pl.peek() == o1  # FIFO head remains o1

        # Pop head
        popped = pl.pop_head()
        assert popped == o1
        assert pl.order_count == 1
        assert pl.total_quantity == 30
        assert pl.peek() == o2

        # Remove remaining order
        removed = pl.remove_order(o2)
        assert removed is True
        assert pl.is_empty() is True
        assert pl.total_quantity == 0


class TestOrderBookCore:
    def test_empty_book_state(self, empty_book):
        assert empty_book.symbol == "AAPL"
        assert empty_book.total_orders == 0
        assert empty_book.get_best_bid() is None
        assert empty_book.get_best_ask() is None
        assert empty_book.get_spread() is None
        assert empty_book.total_bid_volume == 0
        assert empty_book.total_ask_volume == 0

    def test_add_bid_orders_price_priority(self, empty_book):
        # Insert bids out of order: 100, 102, 101
        o1 = Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 100.0)
        o2 = Order("B2", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 20, 102.0)
        o3 = Order("B3", "T3", "AAPL", OrderSide.BUY, OrderType.LIMIT, 15, 101.0)

        empty_book.add_order(o1)
        empty_book.add_order(o2)
        empty_book.add_order(o3)

        assert empty_book.total_orders == 3
        assert empty_book.total_bid_volume == 45
        assert empty_book.get_best_bid() == 102.0  # Highest bid first
        assert empty_book._bid_prices == [102.0, 101.0, 100.0]

    def test_add_ask_orders_price_priority(self, empty_book):
        # Insert asks out of order: 105, 103, 104
        o1 = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 10, 105.0)
        o2 = Order("S2", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 20, 103.0)
        o3 = Order("S3", "T3", "AAPL", OrderSide.SELL, OrderType.LIMIT, 15, 104.0)

        empty_book.add_order(o1)
        empty_book.add_order(o2)
        empty_book.add_order(o3)

        assert empty_book.total_orders == 3
        assert empty_book.total_ask_volume == 45
        assert empty_book.get_best_ask() == 103.0  # Lowest ask first
        assert empty_book._ask_prices == [103.0, 104.0, 105.0]

    def test_spread_calculation(self, empty_book):
        empty_book.add_order(Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 150.0))
        empty_book.add_order(Order("S1", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 10, 152.5))

        assert empty_book.get_best_bid() == 150.0
        assert empty_book.get_best_ask() == 152.5
        assert empty_book.get_spread() == 2.5

    def test_fifo_time_priority_at_same_price(self, empty_book):
        o1 = Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        o2 = Order("B2", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 30, 100.0)
        o3 = Order("B3", "T3", "AAPL", OrderSide.BUY, OrderType.LIMIT, 20, 100.0)

        empty_book.add_order(o1)
        empty_book.add_order(o2)
        empty_book.add_order(o3)

        orders_at_100 = empty_book.get_orders_at_price(OrderSide.BUY, 100.0)
        assert len(orders_at_100) == 3
        assert [o.order_id for o in orders_at_100] == ["B1", "B2", "B3"]

        # Check PriceLevel aggregation
        pl = empty_book.bids[100.0]
        assert pl.total_quantity == 100
        assert pl.order_count == 3

    def test_cancel_order_removes_from_book(self, empty_book):
        o1 = Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        o2 = Order("B2", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 30, 100.0)
        empty_book.add_order(o1)
        empty_book.add_order(o2)

        # Cancel first order
        cancelled = empty_book.cancel_order("B1")
        assert cancelled.status == OrderStatus.CANCELLED
        assert empty_book.total_orders == 1
        assert empty_book.total_bid_volume == 30
        assert empty_book.bids[100.0].total_quantity == 30

        # Cancel second order (cleans up entire price level)
        cancelled2 = empty_book.cancel_order("B2")
        assert cancelled2.status == OrderStatus.CANCELLED
        assert empty_book.total_orders == 0
        assert 100.0 not in empty_book.bids
        assert empty_book.get_best_bid() is None
        assert empty_book._bid_prices == []

    def test_cancel_non_existent_order_raises(self, empty_book):
        with pytest.raises(ValueError, match="not found"):
            empty_book.cancel_order("UNKNOWN-ID")

    def test_remove_order(self, empty_book):
        o1 = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 105.0)
        empty_book.add_order(o1)
        assert empty_book.total_orders == 1

        removed = empty_book.remove_order("S1")
        assert removed == o1
        assert empty_book.total_orders == 0
        assert empty_book.get_best_ask() is None

    def test_market_depth(self, empty_book):
        empty_book.add_order(Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 100.0))
        empty_book.add_order(Order("B2", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 20, 101.0))
        empty_book.add_order(Order("S1", "T3", "AAPL", OrderSide.SELL, OrderType.LIMIT, 30, 105.0))
        empty_book.add_order(Order("S2", "T4", "AAPL", OrderSide.SELL, OrderType.LIMIT, 40, 106.0))

        depth = empty_book.get_depth(max_levels=5)
        assert depth["symbol"] == "AAPL"
        assert depth["best_bid"] == 101.0
        assert depth["best_ask"] == 105.0
        assert depth["spread"] == 4.0

        # Bids sorted descending
        assert depth["bids"][0]["price"] == 101.0
        assert depth["bids"][0]["quantity"] == 20
        assert depth["bids"][1]["price"] == 100.0
        assert depth["bids"][1]["quantity"] == 10

        # Asks sorted ascending
        assert depth["asks"][0]["price"] == 105.0
        assert depth["asks"][0]["quantity"] == 30
        assert depth["asks"][1]["price"] == 106.0
        assert depth["asks"][1]["quantity"] == 40

    def test_validation_errors_on_add(self, empty_book):
        # Symbol mismatch
        with pytest.raises(ValueError, match="Symbol mismatch"):
            empty_book.add_order(Order("O1", "T1", "MSFT", OrderSide.BUY, OrderType.LIMIT, 10, 100.0))

        # Duplicate ID
        o1 = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 100.0)
        empty_book.add_order(o1)
        with pytest.raises(ValueError, match="already exists"):
            empty_book.add_order(o1)

        # Market order directly into book
        m_order = Order("M1", "T1", "AAPL", OrderSide.BUY, OrderType.MARKET, 10)
        with pytest.raises(ValueError, match="Only LIMIT orders"):
            empty_book.add_order(m_order)

    def test_concurrent_order_submission(self, empty_book):
        """Verify thread-safety when submitting orders concurrently."""
        num_threads = 8
        orders_per_thread = 50

        def submit_orders(thread_id: int):
            for i in range(orders_per_thread):
                oid = f"TH{thread_id}-ORD{i}"
                side = OrderSide.BUY if i % 2 == 0 else OrderSide.SELL
                price = 100.0 + (i % 10) if side == OrderSide.BUY else 120.0 + (i % 10)
                order = Order(oid, f"T{thread_id}", "AAPL", side, OrderType.LIMIT, 10, price)
                empty_book.add_order(order)

        threads = [threading.Thread(target=submit_orders, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected_total = num_threads * orders_per_thread
        assert empty_book.total_orders == expected_total
        assert empty_book.total_bid_volume + empty_book.total_ask_volume == expected_total * 10
        assert empty_book.get_best_bid() is not None
        assert empty_book.get_best_ask() is not None
