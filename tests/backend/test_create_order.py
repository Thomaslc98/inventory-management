"""
Tests for the POST /api/orders endpoint (restocking order creation).
"""
import pytest
from datetime import datetime

import mock_data


@pytest.fixture(autouse=True)
def restore_orders():
    """Restore the in-memory orders list after each test.

    POST /api/orders appends to the module-level orders list, which is shared
    across the whole test session. Snapshot and restore so created orders don't
    leak into other tests.
    """
    original = list(mock_data.orders)
    yield
    mock_data.orders[:] = original


class TestCreateOrderEndpoint:
    """Test suite for creating restocking orders."""

    def _sample_payload(self):
        """A valid create-order request body."""
        return {
            "items": [
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly",
                 "quantity": 100, "unit_price": 24.99},
                {"sku": "SNS-300", "name": "Temperature Sensor",
                 "quantity": 50, "unit_price": 12.50},
            ]
        }

    def test_create_order_success(self, client):
        """Test that a restocking order is created and returned."""
        response = client.post("/api/orders", json=self._sample_payload())
        assert response.status_code == 201

        order = response.json()
        # Required Order fields are present
        for field in ("id", "order_number", "customer", "items", "status",
                      "order_date", "expected_delivery", "total_value"):
            assert field in order

        assert order["status"] == "Submitted"
        assert order["customer"] == "Internal Restock"
        assert order["order_number"].startswith("ORD-")
        # Restock orders use an "R" prefix in the sequence portion
        assert "-R" in order["order_number"]

    def test_create_order_total_value_calculation(self, client):
        """Test that total_value equals sum(quantity * unit_price)."""
        payload = self._sample_payload()
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        expected_total = sum(i["quantity"] * i["unit_price"] for i in payload["items"])
        assert abs(order["total_value"] - expected_total) < 0.01

    def test_create_order_lead_time_is_14_days(self, client):
        """Test that expected_delivery is 14 days after order_date."""
        response = client.post("/api/orders", json=self._sample_payload())
        assert response.status_code == 201

        order = response.json()
        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        lead_time_days = (expected_delivery - order_date).days
        assert lead_time_days == 14

    def test_create_order_appears_in_get_orders(self, client):
        """Test that a created order is returned by a subsequent GET /api/orders."""
        response = client.post("/api/orders", json=self._sample_payload())
        assert response.status_code == 201
        new_id = response.json()["id"]

        all_orders = client.get("/api/orders").json()
        assert any(o["id"] == new_id and o["status"] == "Submitted" for o in all_orders)

    def test_create_order_custom_customer(self, client):
        """Test that a provided customer name is preserved."""
        payload = self._sample_payload()
        payload["customer"] = "Restock Bot"
        response = client.post("/api/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["customer"] == "Restock Bot"

    def test_create_order_empty_items_rejected(self, client):
        """Test that an order with no items returns a 400 error."""
        response = client.post("/api/orders", json={"items": []})
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_order_missing_items_validation(self, client):
        """Test that a missing items field returns a 422 validation error."""
        response = client.post("/api/orders", json={"customer": "Nobody"})
        assert response.status_code == 422
