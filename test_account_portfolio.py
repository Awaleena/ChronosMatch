"""
Comprehensive Unit Tests for Account, Holding, Portfolio & AccountService
"""
import pytest
import sys
import os

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.account import Account, Holding, TransactionType
from app.models.order import Order, OrderSide, OrderType, OrderStatus, reset_sequence_counter
from app.models.trade import Trade
from app.services.account_service import AccountService


@pytest.fixture(autouse=True)
def reset_seq():
    reset_sequence_counter()


@pytest.fixture
def service():
    srv = AccountService()
    srv.clear()
    return srv


class TestAccountDomainModel:
    def test_account_creation_default_balance(self):
        acc = Account("ACC-1", initial_cash=100000.0)
        assert acc.account_id == "ACC-1"
        assert acc.cash_balance == 100000.0
        assert acc.reserved_cash == 0.0
        assert acc.available_cash == 100000.0
        assert len(acc.transactions) == 1
        assert acc.transactions[0].tx_type == TransactionType.DEPOSIT
        assert acc.transactions[0].amount == 100000.0

    def test_deposit_and_withdraw(self):
        acc = Account("ACC-2", initial_cash=50000.0)
        acc.deposit(25000.0)
        assert acc.cash_balance == 75000.0
        assert acc.available_cash == 75000.0

        acc.withdraw(10000.0)
        assert acc.cash_balance == 65000.0
        assert acc.available_cash == 65000.0

        # Cannot withdraw more than available cash
        with pytest.raises(ValueError, match="Insufficient available cash"):
            acc.withdraw(70000.0)

    def test_cash_reservation_lifecycle(self):
        acc = Account("ACC-3", initial_cash=10000.0)
        acc.reserve_cash(4000.0)
        assert acc.cash_balance == 10000.0
        assert acc.reserved_cash == 4000.0
        assert acc.available_cash == 6000.0

        # Cannot reserve more than available
        with pytest.raises(ValueError, match="Insufficient funds"):
            acc.reserve_cash(7000.0)

        # Release cash
        acc.release_cash(1500.0)
        assert acc.reserved_cash == 2500.0
        assert acc.available_cash == 7500.0

    def test_holding_reservation_lifecycle(self):
        acc = Account("ACC-4", initial_cash=100000.0)
        # Manually give some holdings for test
        acc.holdings["AAPL"] = Holding("AAPL", quantity=100, average_buy_price=150.0)

        assert acc.holdings["AAPL"].available_quantity == 100

        acc.reserve_shares("AAPL", 40)
        assert acc.holdings["AAPL"].reserved_quantity == 40
        assert acc.holdings["AAPL"].available_quantity == 60

        # Over-reserve shares raises
        with pytest.raises(ValueError, match="Insufficient shares"):
            acc.reserve_shares("AAPL", 70)

        # Release shares
        acc.release_shares("AAPL", 20)
        assert acc.holdings["AAPL"].reserved_quantity == 20
        assert acc.holdings["AAPL"].available_quantity == 80

    def test_settle_buy_and_weighted_average_price(self):
        acc = Account("ACC-BUYER", initial_cash=100000.0)
        # Reserve 50,000 for order
        acc.reserve_cash(50000.0)

        # First buy: 100 shares @ 150.0 = 15,000
        acc.settle_buy("AAPL", quantity=100, execution_price=150.0, reserved_price=150.0)
        assert acc.cash_balance == 85000.0
        assert acc.reserved_cash == 35000.0
        assert acc.holdings["AAPL"].quantity == 100
        assert acc.holdings["AAPL"].average_buy_price == 150.0

        # Second buy: 100 shares @ 200.0 = 20,000
        # Weighted average = (100*150 + 100*200) / 200 = 35000 / 200 = 175.0
        acc.settle_buy("AAPL", quantity=100, execution_price=200.0, reserved_price=200.0)
        assert acc.cash_balance == 65000.0
        assert acc.holdings["AAPL"].quantity == 200
        assert acc.holdings["AAPL"].average_buy_price == 175.0

    def test_settle_sell_and_proceeds(self):
        acc = Account("ACC-SELLER", initial_cash=10000.0)
        acc.holdings["AAPL"] = Holding("AAPL", quantity=100, average_buy_price=150.0)
        acc.reserve_shares("AAPL", 100)

        # Sell 60 shares @ 160.0 = 9,600 proceeds
        acc.settle_sell("AAPL", quantity=60, execution_price=160.0, reserved=True)
        assert acc.cash_balance == 19600.0
        assert acc.holdings["AAPL"].quantity == 40
        assert acc.holdings["AAPL"].reserved_quantity == 40
        assert acc.holdings["AAPL"].average_buy_price == 150.0

    def test_portfolio_valuation_with_pnl(self):
        acc = Account("ACC-PORT", initial_cash=50000.0)
        acc.holdings["AAPL"] = Holding("AAPL", quantity=100, average_buy_price=150.0)  # cost basis = 15,000
        acc.holdings["MSFT"] = Holding("MSFT", quantity=50, average_buy_price=300.0)   # cost basis = 15,000

        # Current market prices: AAPL rose to 170 (+2,000), MSFT dropped to 280 (-1,000)
        market_prices = {"AAPL": 170.0, "MSFT": 280.0}
        valuation = acc.get_portfolio_valuation(market_prices)

        assert valuation["cash_balance"] == 50000.0
        assert valuation["total_holdings_value"] == (100 * 170.0) + (50 * 280.0)  # 17,000 + 14,000 = 31,000
        assert valuation["total_portfolio_value"] == 50000.0 + 31000.0  # 81,000
        assert valuation["total_unrealized_pnl"] == 1000.0  # +2000 - 1000 = +1000


class TestAccountService:
    def test_account_creation_and_retrieval(self, service):
        acc = service.create_account("TRADER-1", initial_cash=75000.0)
        assert acc.account_id == "TRADER-1"
        assert acc.cash_balance == 75000.0

        retrieved = service.get_account("TRADER-1")
        assert retrieved == acc

        with pytest.raises(ValueError, match="already exists"):
            service.create_account("TRADER-1")

    def test_validate_and_reserve_buy(self, service):
        service.create_account("BUYER", initial_cash=20000.0)
        order = Order("B1", "BUYER", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 150.0)

        # 100 * 150 = 15,000 required, account has 20,000 -> succeeds
        service.validate_and_reserve(order)
        acc = service.get_account("BUYER")
        assert acc.reserved_cash == 15000.0
        assert acc.available_cash == 5000.0

        # Second order requiring 10,000 -> fails because only 5,000 available
        order2 = Order("B2", "BUYER", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 100.0)
        with pytest.raises(ValueError, match="Insufficient funds"):
            service.validate_and_reserve(order2)

    def test_validate_and_reserve_sell(self, service):
        acc = service.create_account("SELLER", initial_cash=10000.0)
        acc.holdings["AAPL"] = Holding("AAPL", quantity=50, average_buy_price=100.0)

        order = Order("S1", "SELLER", "AAPL", OrderSide.SELL, OrderType.LIMIT, 30, 120.0)
        service.validate_and_reserve(order)
        assert acc.holdings["AAPL"].reserved_quantity == 30
        assert acc.holdings["AAPL"].available_quantity == 20

        # Second sell order for 30 shares fails (only 20 available)
        order2 = Order("S2", "SELLER", "AAPL", OrderSide.SELL, OrderType.LIMIT, 30, 120.0)
        with pytest.raises(ValueError, match="Insufficient shares"):
            service.validate_and_reserve(order2)

    def test_settle_trade_between_buyer_and_seller(self, service):
        buyer = service.create_account("BUYER", initial_cash=100000.0)
        seller = service.create_account("SELLER", initial_cash=50000.0)
        seller.holdings["AAPL"] = Holding("AAPL", quantity=100, average_buy_price=140.0)

        # Buyer places order for 50 @ 150.0
        buy_order = Order("B1", "BUYER", "AAPL", OrderSide.BUY, OrderType.LIMIT, 50, 150.0)
        service.validate_and_reserve(buy_order)

        # Seller places order for 50 @ 150.0
        sell_order = Order("S1", "SELLER", "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 150.0)
        service.validate_and_reserve(sell_order)

        # Trade executes for 50 @ 150.0 = 7,500
        trade = Trade(
            trade_id="TRD-1",
            symbol="AAPL",
            buy_order_id="B1",
            sell_order_id="S1",
            quantity=50,
            execution_price=150.0,
        )

        service.settle_trade(trade, buy_order, sell_order)

        # Buyer checks
        assert buyer.cash_balance == 92500.0
        assert buyer.reserved_cash == 0.0
        assert buyer.holdings["AAPL"].quantity == 50
        assert buyer.holdings["AAPL"].average_buy_price == 150.0

        # Seller checks
        assert seller.cash_balance == 57500.0
        assert seller.holdings["AAPL"].quantity == 50
        assert seller.holdings["AAPL"].reserved_quantity == 0

    def test_release_order_reservation_on_cancellation(self, service):
        buyer = service.create_account("BUYER", initial_cash=50000.0)
        order = Order("B1", "BUYER", "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 200.0)
        service.validate_and_reserve(order)
        assert buyer.reserved_cash == 20000.0

        # Partial fill of 40 leaves 60 remaining
        order.fill(40)
        buyer.reserved_cash -= 8000.0  # simulate fill unreserve

        # Order is now cancelled
        order.cancel()
        service.release_order_reservation(order)

        # The remaining 60 * 200 = 12,000 should be released
        assert buyer.reserved_cash == 0.0
        assert buyer.available_cash == 50000.0
