"""
Comprehensive Unit Tests for ChronosMatch Price-Time Priority Matching Engine
"""
import pytest
import sys
import os

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.order import Order, OrderSide, OrderType, OrderStatus, reset_sequence_counter
from app.models.trade import Trade
from app.matching.engine import MatchingEngine


@pytest.fixture(autouse=True)
def reset_seq():
    reset_sequence_counter()


@pytest.fixture
def engine():
    return MatchingEngine("AAPL")


class TestMatchingEngine:
    def test_full_fill_exact_match(self, engine):
        # Resting ask: 100 @ 150.0
        ask = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 100, 150.0)
        engine.process_order(ask)
        assert engine.order_book.total_orders == 1
        assert engine.order_book.get_best_ask() == 150.0

        # Incoming bid: 100 @ 150.0
        bid = Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 150.0)
        updated_bid, trades = engine.process_order(bid)

        # Verification
        assert updated_bid.status == OrderStatus.FILLED
        assert updated_bid.remaining_quantity == 0
        assert ask.status == OrderStatus.FILLED
        assert ask.remaining_quantity == 0
        assert len(trades) == 1

        t = trades[0]
        assert t.symbol == "AAPL"
        assert t.quantity == 100
        assert t.execution_price == 150.0
        assert t.buy_order_id == "B1"
        assert t.sell_order_id == "S1"
        assert t.maker_order_id == "S1"
        assert t.taker_order_id == "B1"

        # Book should be empty
        assert engine.order_book.total_orders == 0
        assert engine.last_traded_price == 150.0
        assert engine.total_traded_volume == 100

    def test_partial_fill_incoming_larger(self, engine):
        # Resting ask: 60 @ 500.0
        ask = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 60, 500.0)
        engine.process_order(ask)

        # Incoming bid: 100 @ 500.0
        bid = Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 500.0)
        updated_bid, trades = engine.process_order(bid)

        assert len(trades) == 1
        assert trades[0].quantity == 60
        assert trades[0].execution_price == 500.0

        # Maker is filled
        assert ask.status == OrderStatus.FILLED
        assert ask.remaining_quantity == 0

        # Taker is partially filled and placed in book as resting bid
        assert updated_bid.status == OrderStatus.PARTIALLY_FILLED
        assert updated_bid.remaining_quantity == 40
        assert updated_bid.filled_quantity == 60

        assert engine.order_book.total_orders == 1
        assert engine.order_book.get_best_bid() == 500.0
        assert engine.order_book.total_bid_volume == 40

    def test_partial_fill_resting_larger(self, engine):
        # Resting bid: 100 @ 500.0
        bid = Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 500.0)
        engine.process_order(bid)

        # Incoming ask: 60 @ 500.0
        ask = Order("S1", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 60, 500.0)
        updated_ask, trades = engine.process_order(ask)

        assert len(trades) == 1
        assert trades[0].quantity == 60
        assert updated_ask.status == OrderStatus.FILLED

        # Maker bid remains in book with 40 units
        assert bid.status == OrderStatus.PARTIALLY_FILLED
        assert bid.remaining_quantity == 40

        assert engine.order_book.total_orders == 1
        assert engine.order_book.get_best_bid() == 500.0
        assert engine.order_book.total_bid_volume == 40

    def test_multiple_price_levels_swept(self, engine):
        # Populate 3 ask levels: 50 @ 101, 50 @ 102, 50 @ 103
        engine.process_order(Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 101.0))
        engine.process_order(Order("S2", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 102.0))
        engine.process_order(Order("S3", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 103.0))

        # Incoming BUY order for 120 @ 103.0
        bid = Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 120, 103.0)
        updated_bid, trades = engine.process_order(bid)

        assert updated_bid.status == OrderStatus.FILLED
        assert len(trades) == 3

        assert trades[0].quantity == 50
        assert trades[0].execution_price == 101.0

        assert trades[1].quantity == 50
        assert trades[1].execution_price == 102.0

        assert trades[2].quantity == 20
        assert trades[2].execution_price == 103.0

        # Level 103 should still have 30 units left
        assert engine.order_book.total_orders == 1
        assert engine.order_book.get_best_ask() == 103.0
        assert engine.order_book.total_ask_volume == 30

    def test_fifo_time_priority_matching(self, engine):
        # Two asks at same price 100: S1 earlier than S2
        s1 = Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0)
        s2 = Order("S2", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0)
        engine.process_order(s1)
        engine.process_order(s2)

        # Incoming buy for 60
        bid = Order("B1", "T3", "AAPL", OrderSide.BUY, OrderType.LIMIT, 60, 100.0)
        _, trades = engine.process_order(bid)

        assert len(trades) == 2
        # First trade against S1 (all 50)
        assert trades[0].sell_order_id == "S1"
        assert trades[0].quantity == 50
        assert s1.status == OrderStatus.FILLED

        # Second trade against S2 (10)
        assert trades[1].sell_order_id == "S2"
        assert trades[1].quantity == 10
        assert s2.remaining_quantity == 40

    def test_maker_price_priority(self, engine):
        # Resting ask at 100.0
        engine.process_order(Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0))

        # Buyer willing to pay 105.0 -> Trade must execute at resting maker price 100.0!
        bid = Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 105.0)
        _, trades = engine.process_order(bid)
        assert trades[0].execution_price == 100.0

        # Conversely: Resting bid at 105.0
        engine.process_order(Order("B2", "T3", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 105.0))

        # Seller willing to sell at 100.0 -> Trade executes at resting maker price 105.0!
        ask = Order("S2", "T4", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0)
        _, trades = engine.process_order(ask)
        assert trades[0].execution_price == 105.0

    def test_no_match_scenario(self, engine):
        # Bid @ 95, Ask @ 100
        engine.process_order(Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 95.0))
        _, trades = engine.process_order(Order("S1", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 10, 100.0))

        assert len(trades) == 0
        assert engine.order_book.total_orders == 2
        assert engine.order_book.get_spread() == 5.0

    def test_market_buy_order_matching(self, engine):
        engine.process_order(Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 40, 100.0))
        engine.process_order(Order("S2", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 60, 102.0))

        market_buy = Order("MB1", "T3", "AAPL", OrderSide.BUY, OrderType.MARKET, 50)
        updated, trades = engine.process_order(market_buy)

        assert updated.status == OrderStatus.FILLED
        assert len(trades) == 2
        assert trades[0].execution_price == 100.0
        assert trades[0].quantity == 40
        assert trades[1].execution_price == 102.0
        assert trades[1].quantity == 10

    def test_market_sell_order_matching(self, engine):
        engine.process_order(Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 150.0))

        market_sell = Order("MS1", "T2", "AAPL", OrderSide.SELL, OrderType.MARKET, 30)
        updated, trades = engine.process_order(market_sell)

        assert updated.status == OrderStatus.FILLED
        assert len(trades) == 1
        assert trades[0].execution_price == 150.0
        assert trades[0].quantity == 30

    def test_market_order_insufficient_liquidity(self, engine):
        # Empty book -> market order rejected
        mb = Order("MB1", "T1", "AAPL", OrderSide.BUY, OrderType.MARKET, 100)
        updated, trades = engine.process_order(mb)
        assert len(trades) == 0
        assert updated.status == OrderStatus.REJECTED

        # Partial liquidity: book has 30, order asks for 100
        engine.process_order(Order("S1", "T2", "AAPL", OrderSide.SELL, OrderType.LIMIT, 30, 100.0))
        mb2 = Order("MB2", "T3", "AAPL", OrderSide.BUY, OrderType.MARKET, 100)
        updated2, trades2 = engine.process_order(mb2)

        assert len(trades2) == 1
        assert trades2[0].quantity == 30
        assert updated2.filled_quantity == 30
        assert updated2.remaining_quantity == 70
        assert updated2.status == OrderStatus.PARTIALLY_FILLED
        # Market orders NEVER rest in book
        assert engine.order_book.total_orders == 0

    def test_order_cancellation_via_engine(self, engine):
        o = Order("B1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        engine.process_order(o)
        assert engine.order_book.total_orders == 1

        cancelled = engine.cancel_order("B1")
        assert cancelled.status == OrderStatus.CANCELLED
        assert engine.order_book.total_orders == 0

    def test_market_summary_and_trade_history(self, engine):
        engine.process_order(Order("S1", "T1", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 100.0))
        engine.process_order(Order("B1", "T2", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0))

        summary = engine.get_market_summary()
        assert summary["symbol"] == "AAPL"
        assert summary["last_traded_price"] == 100.0
        assert summary["total_traded_volume"] == 50
        assert summary["total_trades_count"] == 1

        recent_trades = engine.get_trades(limit=10)
        assert len(recent_trades) == 1
        assert recent_trades[0]["execution_price"] == 100.0
        assert recent_trades[0]["quantity"] == 50
