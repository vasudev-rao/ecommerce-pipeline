"""Unit tests for etl/transform/clean.py"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from etl.transform.clean import DataCleaner


@pytest.fixture()
def cleaner():
    return DataCleaner()


def make_orders(n=5, **overrides):
    now = datetime.now(timezone.utc)
    data = {
        "order_id":       list(range(1, n + 1)),
        "customer_id":    list(range(101, 101 + n)),
        "status":         ["delivered"] * n,
        "total_amount":   [100.0 + i * 10 for i in range(n)],
        "discount_amount":[5.0] * n,
        "shipping_amount":[0.0] * n,
        "currency":       ["USD"] * n,
        "payment_method": ["credit_card"] * n,
        "order_date":     ["2024-01-15"] * n,
        "customer_country": ["US"] * n,
        "updated_at":     [now] * n,
    }
    for k, v in overrides.items():
        data[k] = v if isinstance(v, list) else [v] * n
    return pd.DataFrame(data)


def make_customers(n=5, **overrides):
    data = {
        "customer_id": list(range(1, n + 1)),
        "email":       [f"user{i}@example.com" for i in range(n)],
        "first_name":  ["John"] * n,
        "last_name":   ["Doe"] * n,
        "country":     ["US"] * n,
        "city":        ["New York"] * n,
        "signup_date": ["2023-01-01"] * n,
        "is_active":   [True] * n,
        "updated_at":  [datetime.now(timezone.utc)] * n,
    }
    for k, v in overrides.items():
        data[k] = v if isinstance(v, list) else [v] * n
    return pd.DataFrame(data)


def make_products(n=5, **overrides):
    data = {
        "product_id": list(range(1, n + 1)),
        "sku":        [f"SKU-{i:04d}" for i in range(n)],
        "name":       [f"Product {i}" for i in range(n)],
        "category":   ["Electronics"] * n,
        "price":      [100.0 + i * 20 for i in range(n)],
        "cost":       [40.0 + i * 8 for i in range(n)],
        "is_active":  [True] * n,
    }
    for k, v in overrides.items():
        data[k] = v if isinstance(v, list) else [v] * n
    return pd.DataFrame(data)


def make_items(n=5, **overrides):
    data = {
        "item_id":     list(range(1, n + 1)),
        "order_id":    list(range(1, n + 1)),
        "product_id":  list(range(1, n + 1)),
        "quantity":    [2] * n,
        "unit_price":  [50.0] * n,
        "discount_pct":[0.0] * n,
    }
    for k, v in overrides.items():
        data[k] = v if isinstance(v, list) else [v] * n
    return pd.DataFrame(data)


# ── Orders ────────────────────────────────────────────────────────────────────

class TestCleanOrders:
    def test_valid_orders_pass_through(self, cleaner):
        df = make_orders()
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert len(clean) == 5
        assert issues == []

    def test_empty_dataframe_returns_empty(self, cleaner):
        clean, issues = cleaner.clean_orders(pd.DataFrame(), "run-001")
        assert clean.empty
        assert issues == []

    def test_null_order_id_dropped(self, cleaner):
        df = make_orders()
        df.loc[0, "order_id"] = None
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert len(clean) == 4
        assert any("null" in i.lower() for i in issues)

    def test_null_customer_id_dropped(self, cleaner):
        df = make_orders()
        df.loc[1, "customer_id"] = None
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert len(clean) == 4

    def test_invalid_status_set_to_pending(self, cleaner):
        df = make_orders(status="invalid_status")
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert (clean["status"] == "pending").all()
        assert any("invalid status" in i.lower() for i in issues)

    def test_zero_amount_dropped(self, cleaner):
        df = make_orders(total_amount=0.0)
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert clean.empty

    def test_negative_amount_dropped(self, cleaner):
        df = make_orders(total_amount=-50.0)
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert clean.empty

    def test_currency_uppercased(self, cleaner):
        df = make_orders(currency="usd")
        clean, _ = cleaner.clean_orders(df, "run-001")
        assert (clean["currency"] == "USD").all()

    def test_unknown_currency_set_to_usd(self, cleaner):
        df = make_orders(currency="XYZ")
        clean, issues = cleaner.clean_orders(df, "run-001")
        assert (clean["currency"] == "USD").all()
        assert any("unknown currency" in i.lower() for i in issues)

    def test_duplicate_order_id_deduplicated(self, cleaner):
        df = make_orders(n=3)
        dup = df.iloc[0:1].copy()
        df = pd.concat([df, dup], ignore_index=True)
        clean, _ = cleaner.clean_orders(df, "run-001")
        assert len(clean) == 3
        assert clean["order_id"].nunique() == 3

    def test_run_id_column_added(self, cleaner):
        df = make_orders()
        clean, _ = cleaner.clean_orders(df, "my-run-id")
        assert "run_id" in clean.columns
        assert (clean["run_id"] == "my-run-id").all()

    def test_input_not_mutated(self, cleaner):
        df = make_orders()
        original_cols = set(df.columns)
        cleaner.clean_orders(df, "run-001")
        assert set(df.columns) == original_cols


# ── Customers ─────────────────────────────────────────────────────────────────

class TestCleanCustomers:
    def test_valid_customers_pass_through(self, cleaner):
        df = make_customers()
        clean, issues = cleaner.clean_customers(df, "run-001")
        assert len(clean) == 5
        assert issues == []

    def test_null_customer_id_dropped(self, cleaner):
        df = make_customers()
        df.loc[0, "customer_id"] = None
        clean, issues = cleaner.clean_customers(df, "run-001")
        assert len(clean) == 4

    def test_invalid_email_dropped(self, cleaner):
        df = make_customers()
        df.loc[0, "email"] = "not-an-email"
        clean, issues = cleaner.clean_customers(df, "run-001")
        assert len(clean) == 4
        assert any("email" in i.lower() for i in issues)

    def test_email_lowercased(self, cleaner):
        df = make_customers(email="USER@EXAMPLE.COM")
        clean, _ = cleaner.clean_customers(df, "run-001")
        assert (clean["email"] == "user@example.com").all()

    def test_name_title_cased(self, cleaner):
        df = make_customers(first_name="john", last_name="doe")
        clean, _ = cleaner.clean_customers(df, "run-001")
        assert (clean["first_name"] == "John").all()

    def test_country_uppercased(self, cleaner):
        df = make_customers(country="us")
        clean, _ = cleaner.clean_customers(df, "run-001")
        assert (clean["country"] == "US").all()


# ── Products ──────────────────────────────────────────────────────────────────

class TestCleanProducts:
    def test_valid_products_pass_through(self, cleaner):
        df = make_products()
        clean, issues = cleaner.clean_products(df, "run-001")
        assert len(clean) == 5
        assert issues == []

    def test_zero_price_dropped(self, cleaner):
        df = make_products(price=0.0)
        clean, _ = cleaner.clean_products(df, "run-001")
        assert clean.empty

    def test_cost_exceeding_price_capped(self, cleaner):
        df = make_products()
        df.loc[0, "cost"] = df.loc[0, "price"] + 10  # cost > price
        clean, issues = cleaner.clean_products(df, "run-001")
        assert clean.loc[clean["product_id"] == 1, "cost"].iloc[0] < clean.loc[clean["product_id"] == 1, "price"].iloc[0]
        assert any("cost >= price" in i.lower() for i in issues)

    def test_margin_pct_computed(self, cleaner):
        df = make_products()
        df["price"] = 100.0
        df["cost"] = 60.0
        clean, _ = cleaner.clean_products(df, "run-001")
        assert (clean["margin_pct"] == 40.0).all()

    def test_sku_uppercased(self, cleaner):
        df = make_products(sku="sku-001")
        clean, _ = cleaner.clean_products(df, "run-001")
        assert (clean["sku"] == "SKU-001").all()


# ── Order items ───────────────────────────────────────────────────────────────

class TestCleanOrderItems:
    def test_valid_items_pass_through(self, cleaner):
        df = make_items()
        clean, issues = cleaner.clean_order_items(df, "run-001")
        assert len(clean) == 5
        assert issues == []

    def test_zero_quantity_dropped(self, cleaner):
        df = make_items(quantity=0)
        clean, _ = cleaner.clean_order_items(df, "run-001")
        assert clean.empty

    def test_line_total_computed(self, cleaner):
        df = make_items(quantity=2, unit_price=50.0, discount_pct=10.0)
        clean, _ = cleaner.clean_order_items(df, "run-001")
        expected = round(2 * 50.0 * (1 - 0.10), 2)
        assert (clean["line_total"] == expected).all()
