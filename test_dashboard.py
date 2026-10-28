"""
Unit Tests for ChronosMatch Dashboard
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Add the backend folder to Python path
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

sys.path.insert(0, BACKEND_DIR)

# Import FastAPI application
from main import app


# Create test client
client = TestClient(app)


def test_dashboard_endpoint():
    """Test /dashboard endpoint."""

    response = client.get("/dashboard")

    assert response.status_code == 200

    assert "ChronosMatch" in response.text
    assert "ORDER BOOK" in response.text
    assert "ORDER PANEL" in response.text
    assert "ENGINE PERFORMANCE" in response.text


def test_dashboard_browser_root():
    """Test the root / endpoint."""

    response = client.get(
        "/",
        headers={
            "accept": "text/html,application/xhtml+xml"
        }
    )

    assert response.status_code == 200
    assert "ChronosMatch" in response.text


def test_static_css_and_js_are_served():
    """Test that CSS and JavaScript files are available via both /static and direct paths."""

    css_response = client.get("/static/style.css")
    js_response = client.get("/static/app.js")

    assert css_response.status_code == 200
    assert js_response.status_code == 200

    # Direct paths for dashboard relative URL resolution
    direct_css = client.get("/style.css")
    direct_js = client.get("/app.js")

    assert direct_css.status_code == 200
    assert "text/css" in direct_css.headers["content-type"]
    assert direct_js.status_code == 200
    assert "javascript" in direct_js.headers["content-type"]
