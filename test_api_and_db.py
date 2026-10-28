"""
Integration Tests for REST API Endpoints & Database Persistence
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from app.services.trading_service import trading_service
from app.database.session import SessionLocal, init_db
from app.database.models import OrderDB, TradeDB, AccountDB

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_engine_and_db():
    init_db()
    trading_service.clear()


class TestRestApiEndpoints:
    def test_account_creation_and_deposit(self):
        # Create account
        res = client.post("/accounts", json={"account_id": "T-API-1", "initial_cash": 100000.0})
        assert res.status_code == 201
        data = res.json()
        assert data["account_id"] == "T-API-1"
        assert data["cash_balance"] == 100000.0
        assert data["available_cash"] == 100000.0

        # Retrieve account
        res_get = client.get("/accounts/T-API-1")
        assert res_get.status_code == 200
        assert res_get.json()["cash_balance"] == 100000.0

        # Deposit
        res_dep = client.post("/accounts/T-API-1/deposit", json={"amount": 25000.0})
        assert res_dep.status_code == 200
        assert res_dep.json()["cash_balance"] == 125000.0

    def test_order_placement_and_orderbook(self):
        # Create buyer account
        client.post("/accounts", json={"account_id": "BUYER-1", "initial_cash": 50000.0})

        # Submit BUY limit order
        order_payload = {
            "trader_id": "BUYER-1",
            "symbol": "AAPL",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 10,
            "price": 150.0,
        }
        res = client.post("/orders", json=order_payload)
        assert res.status_code == 201
        order_data = res.json()
        assert order_data["symbol"] == "AAPL"
        assert order_data["side"] == "BUY"
        assert order_data["quantity"] == 10
        assert order_data["remaining_quantity"] == 10
        assert order_data["status"] == "PENDING"
        order_id = order_data["order_id"]

        # Check orderbook
        res_ob = client.get("/orderbook/AAPL")
        assert res_ob.status_code == 200
        ob_data = res_ob.json()
        assert ob_data["best_bid"] == 150.0
        assert len(ob_data["bids"]) == 1
        assert ob_data["bids"][0]["quantity"] == 10

        # Check order list
        res_list = client.get("/orders?symbol=AAPL")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 1

        # Check single order
        res_single = client.get(f"/orders/{order_id}")
        assert res_single.status_code == 200
        assert res_single.json()["order_id"] == order_id

    def test_trade_execution_between_accounts_via_api(self):
        # Setup Buyer and Seller
        client.post("/accounts", json={"account_id": "TRADER-BUY", "initial_cash": 50000.0})
        seller_acc = trading_service.account_service.create_account("TRADER-SELL", initial_cash=10000.0)
        # Give seller 50 shares of AAPL
        seller_acc.holdings["AAPL"] = seller_acc.holdings.get("AAPL") or None
        from app.models.account import Holding
        seller_acc.holdings["AAPL"] = Holding("AAPL", quantity=50, average_buy_price=140.0)

        # Place BUY order: 20 @ 150.0
        client.post(
            "/orders",
            json={
                "trader_id": "TRADER-BUY",
                "symbol": "AAPL",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 20,
                "price": 150.0,
            },
        )

        # Place SELL order: 20 @ 150.0
        res_sell = client.post(
            "/orders",
            json={
                "trader_id": "TRADER-SELL",
                "symbol": "AAPL",
                "side": "SELL",
                "order_type": "LIMIT",
                "quantity": 20,
                "price": 150.0,
            },
        )
        assert res_sell.status_code == 201
        sell_data = res_sell.json()
        assert sell_data["status"] == "FILLED"
        assert len(sell_data["trades"]) == 1

        trade_info = sell_data["trades"][0]
        assert trade_info["quantity"] == 20
        assert trade_info["execution_price"] == 150.0
        trade_id = trade_info["trade_id"]

        # Check trades endpoint
        res_trades = client.get("/trades?symbol=AAPL")
        assert res_trades.status_code == 200
        assert len(res_trades.json()) == 1

        # Check single trade endpoint
        res_trd = client.get(f"/trades/{trade_id}")
        assert res_trd.status_code == 200
        assert res_trd.json()["trade_id"] == trade_id

        # Verify portfolio of Buyer
        res_port = client.get("/portfolio/TRADER-BUY")
        assert res_port.status_code == 200
        port_data = res_port.json()
        assert port_data["cash_balance"] == 50000.0 - (20 * 150.0)  # 47,000
        assert len(port_data["holdings"]) == 1
        assert port_data["holdings"][0]["symbol"] == "AAPL"
        assert port_data["holdings"][0]["quantity"] == 20

    def test_cancel_order_via_api(self):
        client.post("/accounts", json={"account_id": "CANCELER", "initial_cash": 20000.0})

        # Place BUY 10 @ 100
        res_order = client.post(
            "/orders",
            json={
                "trader_id": "CANCELER",
                "symbol": "MSFT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 10,
                "price": 100.0,
            },
        )
        order_id = res_order.json()["order_id"]

        # Cancel order
        res_cancel = client.delete(f"/orders/{order_id}")
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "CANCELLED"

        # Verify orderbook for MSFT is empty
        ob = client.get("/orderbook/MSFT").json()
        assert ob["best_bid"] is None

        # Verify account cash unreserved
        acc = client.get("/accounts/CANCELER").json()
        assert acc["reserved_cash"] == 0.0
        assert acc["available_cash"] == 20000.0

    def test_market_summary_endpoints(self):
        client.post("/accounts", json={"account_id": "T1", "initial_cash": 50000.0})
        client.post(
            "/orders",
            json={
                "trader_id": "T1",
                "symbol": "TSLA",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 10,
                "price": 200.0,
            },
        )

        res = client.get("/market/TSLA")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "TSLA"
        assert data["best_bid"] == 200.0

        # All markets
        res_all = client.get("/market")
        assert res_all.status_code == 200
        assert isinstance(res_all.json(), list)

    def test_database_persistence_verification(self):
        # Create an account and execute an order
        client.post("/accounts", json={"account_id": "DB-TRADER", "initial_cash": 50000.0})
        res = client.post(
            "/orders",
            json={
                "trader_id": "DB-TRADER",
                "symbol": "BTC-USD",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 1,
                "price": 60000.0,
            },
        )
        # Should fail due to insufficient funds (needs 60,000, has 50,000)
        assert res.status_code == 400
        assert "Insufficient funds" in res.json()["detail"]

        # Deposit 20,000 more
        client.post("/accounts/DB-TRADER/deposit", json={"amount": 20000.0})

        # Retry with sufficient funds
        res2 = client.post(
            "/orders",
            json={
                "trader_id": "DB-TRADER",
                "symbol": "BTC-USD",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 1,
                "price": 60000.0,
            },
        )
        assert res2.status_code == 201
        order_id = res2.json()["order_id"]

        # Verify record exists in SQLite via SQLAlchemy session
        db = SessionLocal()
        try:
            db_order = db.query(OrderDB).filter(OrderDB.order_id == order_id).first()
            assert db_order is not None
            assert db_order.symbol == "BTC-USD"
            assert db_order.price == 60000.0

            db_acc = db.query(AccountDB).filter(AccountDB.account_id == "DB-TRADER").first()
            assert db_acc is not None
            assert db_acc.cash_balance == 70000.0
            assert db_acc.reserved_cash == 60000.0
        finally:
            db.close()
