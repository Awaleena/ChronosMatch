"""
Unit tests for Share Deposit functionality in Account Model, Service, and API
"""
import pytest
from fastapi.testclient import TestClient

from app.models.account import Account
from app.services.account_service import AccountService
from main import app


def test_account_model_deposit_shares():
    acc = Account("TRADER_TEST", initial_cash=50000.0)
    assert "TCS" not in acc.holdings
    
    h = acc.deposit_shares("TCS", 100, price=3200.0)
    assert h.quantity == 100
    assert h.average_buy_price == 3200.0
    assert acc.holdings["TCS"].available_quantity == 100

    # Add more at different price to test weighted average calculation
    h2 = acc.deposit_shares("TCS", 100, price=3400.0)
    assert h2.quantity == 200
    assert h2.average_buy_price == 3300.0


def test_account_service_deposit_shares():
    svc = AccountService()
    acc = svc.deposit_shares("ACC_MM_1", "RELIANCE", 50, price=2500.0)
    assert "RELIANCE" in acc.holdings
    assert acc.holdings["RELIANCE"].quantity == 50


def test_api_deposit_shares():
    client = TestClient(app)
    # Deposit shares via API
    resp = client.post(
        "/api/v1/accounts/TEST_MM_API/deposit-shares",
        json={"symbol": "INFY", "quantity": 75, "average_price": 1450.0}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "INFY" in data["holdings"]
    assert data["holdings"]["INFY"]["quantity"] == 75
    assert data["holdings"]["INFY"]["average_buy_price"] == 1450.0
