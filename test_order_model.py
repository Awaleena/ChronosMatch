"""
Comprehensive Unit Tests for Core Order Model & Validation Schemas
"""
import pytest
from pydantic import ValidationError
import sys
import os

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.order import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    get_next_sequence_number,
    reset_sequence_counter,
)
from app.schemas.order import (
    OrderCreateRequest,
    OrderResponse,
    OrderCancelRequest,
    OrderCancelResponse,
)


@pytest.fixture(autouse=True)
def reset_seq():
    reset_sequence_counter()


class TestOrderDomainModel:
    def test_create_valid_limit_buy_order(self):
        order = Order(
            order_id="ORD-001",
            trader_id="TRADER-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=150.50,
        )

        assert order.order_id == "ORD-001"
        assert order.trader_id == "TRADER-1"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == 100
        assert order.remaining_quantity == 100
        assert order.filled_quantity == 0
        assert order.price == 150.50
        assert order.status == OrderStatus.PENDING
        assert order.is_active is True
        assert order.is_filled is False
        assert order.sequence_number == 1
        assert order.timestamp > 0

    def test_create_valid_limit_sell_order(self):
        order = Order(
            order_id="ORD-002",
            trader_id="TRADER-2",
            symbol="msft",  # should be normalized to uppercase
            side="SELL",
            order_type="LIMIT",
            quantity=50,
            price=320.75555,
        )

        assert order.symbol == "MSFT"
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.LIMIT
        assert order.price == 320.7556  # rounded to 4 decimals

    def test_create_valid_market_orders(self):
        buy_market = Order(
            order_id="ORD-003",
            trader_id="TRADER-1",
            symbol="TSLA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=25,
            price=None,
        )
        assert buy_market.price == 0.0
        assert buy_market.order_type == OrderType.MARKET

        sell_market = Order(
            order_id="ORD-004",
            trader_id="TRADER-2",
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=10,
            price=0.0,
        )
        assert sell_market.price == 0.0

    def test_sequence_number_monotonically_increases(self):
        o1 = Order("1", "T", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 100.0)
        o2 = Order("2", "T", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 100.0)
        o3 = Order("3", "T", "AAPL", OrderSide.BUY, OrderType.LIMIT, 10, 100.0)

        assert o1.sequence_number < o2.sequence_number < o3.sequence_number

    @pytest.mark.parametrize(
        "kwargs,error_match",
        [
            (dict(order_id="", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=100.0), "order_id"),
            (dict(order_id="1", trader_id="", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=100.0), "trader_id"),
            (dict(order_id="1", trader_id="T", symbol="", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=100.0), "symbol"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side="INVALID", order_type=OrderType.LIMIT, quantity=10, price=100.0), "Invalid order side"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type="INVALID", quantity=10, price=100.0), "Invalid order type"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0, price=100.0), "positive integer"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=-5, price=100.0), "positive integer"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=None), "LIMIT orders require a price > 0"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=-10.0), "LIMIT orders require a price > 0"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=0.0), "LIMIT orders require a price > 0"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=100.0, remaining_quantity=20), "remaining_quantity"),
            (dict(order_id="1", trader_id="T", symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=100.0, remaining_quantity=-1), "remaining_quantity"),
        ],
    )
    def test_invalid_order_initialization_raises(self, kwargs, error_match):
        with pytest.raises(ValueError, match=error_match):
            Order(**kwargs)

    def test_order_fill_lifecycle(self):
        order = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 150.0)

        # Partial fill 1
        rem = order.fill(40)
        assert rem == 60
        assert order.remaining_quantity == 60
        assert order.filled_quantity == 40
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.is_active is True
        assert order.is_filled is False

        # Partial fill 2
        rem = order.fill(60)
        assert rem == 0
        assert order.remaining_quantity == 0
        assert order.filled_quantity == 100
        assert order.status == OrderStatus.FILLED
        assert order.is_active is False
        assert order.is_filled is True

        # Overfill raises
        with pytest.raises(ValueError, match="Cannot fill inactive order"):
            order.fill(1)

    def test_overfill_active_order_raises(self):
        order = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        with pytest.raises(ValueError, match="only 50 remaining"):
            order.fill(51)

    def test_fill_with_invalid_quantities(self):
        order = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        with pytest.raises(ValueError, match="positive integer"):
            order.fill(0)
        with pytest.raises(ValueError, match="positive integer"):
            order.fill(-10)

    def test_order_cancellation(self):
        order = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        order.cancel()
        assert order.status == OrderStatus.CANCELLED
        assert order.is_active is False

        # Cannot cancel again
        with pytest.raises(ValueError, match="already cancelled"):
            order.cancel()

    def test_cannot_cancel_filled_order(self):
        order = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 100.0)
        order.fill(50)
        with pytest.raises(ValueError, match="Cannot cancel completely filled"):
            order.cancel()

    def test_to_dict_structure(self):
        order = Order("O-123", "T-456", "GOOGL", OrderSide.SELL, OrderType.LIMIT, 20, 180.0)
        d = order.to_dict()
        assert d["order_id"] == "O-123"
        assert d["trader_id"] == "T-456"
        assert d["symbol"] == "GOOGL"
        assert d["side"] == "SELL"
        assert d["order_type"] == "LIMIT"
        assert d["quantity"] == 20
        assert d["remaining_quantity"] == 20
        assert d["filled_quantity"] == 0
        assert d["price"] == 180.0
        assert d["status"] == "PENDING"
        assert isinstance(d["timestamp"], float)
        assert isinstance(d["sequence_number"], int)


class TestOrderSchemas:
    def test_valid_order_create_request_limit(self):
        req = OrderCreateRequest(
            trader_id="T1",
            symbol="aapl",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=150.0,
        )
        assert req.symbol == "AAPL"
        assert req.price == 150.0

    def test_valid_order_create_request_market(self):
        req = OrderCreateRequest(
            trader_id="T1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        assert req.price == 0.0

    def test_limit_order_missing_price_raises_validation_error(self):
        with pytest.raises(ValidationError):
            OrderCreateRequest(
                trader_id="T1",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                price=None,
            )

    def test_limit_order_non_positive_price_raises_validation_error(self):
        with pytest.raises(ValidationError):
            OrderCreateRequest(
                trader_id="T1",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                price=0.0,
            )

    def test_non_positive_quantity_raises_validation_error(self):
        with pytest.raises(ValidationError):
            OrderCreateRequest(
                trader_id="T1",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=0,
                price=100.0,
            )

    def test_order_response_model(self):
        order = Order("O1", "T1", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 150.0)
        res = OrderResponse(**order.to_dict())
        assert res.order_id == "O1"
        assert res.status == OrderStatus.PENDING
        assert res.remaining_quantity == 100
        assert res.filled_quantity == 0

    def test_order_cancel_request_and_response(self):
        req = OrderCancelRequest(order_id="O1")
        assert req.order_id == "O1"

        res = OrderCancelResponse(
            order_id="O1",
            status=OrderStatus.CANCELLED,
            message="Order cancelled successfully",
            remaining_quantity_cancelled=50,
        )
        assert res.status == OrderStatus.CANCELLED
        assert res.remaining_quantity_cancelled == 50
