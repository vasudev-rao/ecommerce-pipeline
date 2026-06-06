"""Unit tests for etl/transform/enrich.py"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from etl.transform.enrich import DataEnricher


@pytest.fixture()
def enricher():
    return DataEnricher()


def make_orders(n=5, **overrides):
    data = {
        "order_id":       list(range(1, n + 1)),
        "customer_id":    [1] * n,
        "status":         ["delivered"] * n,
        "total_amount":   [100.0 + i * 50 for i in range(n)],
        "discount_amount":[5.0] * n,
        "order_date":     ["2024-01-15"] * n,
        "net_revenue":    [95.0 + i * 50 for i in range(n)],
    }
    for k, v in overrides.items():
        data[k] = v if isinstance(v, list) else [v] * n
    return pd.DataFrame(data)


def make_customers(n=3):
    return pd.DataFrame({
        "customer_id": list(range(1, n + 1)),
        "signup_date": ["2023-01-01"] * n,
        "is_active":   [True] * n,
    })


def make_products(n=5):
    return pd.DataFrame({
        "product_id": list(range(1, n + 1)),
        "name":       [f"Product {i}" for i in range(n)],
        "price":      [10.0, 50.0, 120.0, 200.0, 500.0],
        "cost":       [3.0, 20.0, 40.0, 60.0, 150.0],
        "margin_pct": [70.0, 60.0, 66.7, 70.0, 70.0],
    })


class TestEnrichOrders:
    def test_revenue_net_computed(self, enricher):
        df = make_orders()
        enriched = enricher.enrich_orders(df)
        assert "revenue_net" in enriched.columns
        assert (enriched["revenue_net"] == enriched["total_amount"] - enriched["discount_amount"]).all()

    def test_high_value_flag(self, enricher):
        df = make_orders(total_amount=[50.0, 150.0, 250.0, 300.0, 100.0])
        enriched = enricher.enrich_orders(df)
        assert enriched.loc[0, "is_high_value"] == False
        assert enriched.loc[2, "is_high_value"] == True

    def test_day_of_week_added(self, enricher):
        df = make_orders()
        enriched = enricher.enrich_orders(df)
        assert "day_of_week" in enriched.columns
        assert enriched["day_of_week"].notna().all()

    def test_time_dimensions_added(self, enricher):
        df = make_orders()
        enriched = enricher.enrich_orders(df)
        for col in ["month", "quarter", "year", "week_of_year", "is_weekend"]:
            assert col in enriched.columns

    def test_empty_dataframe_returned_unchanged(self, enricher):
        result = enricher.enrich_orders(pd.DataFrame())
        assert result.empty


class TestEnrichCustomers:
    def test_order_count_computed(self, enricher):
        customers = make_customers(n=2)
        orders = make_orders(n=4, customer_id=[1, 1, 2, 1], status="delivered")
        enriched = enricher.enrich_customers(customers, orders)
        c1 = enriched.loc[enriched["customer_id"] == 1, "order_count"].iloc[0]
        c2 = enriched.loc[enriched["customer_id"] == 2, "order_count"].iloc[0]
        assert c1 == 3
        assert c2 == 1

    def test_customer_segment_new(self, enricher):
        customers = make_customers(n=1)
        orders = make_orders(n=1, customer_id=1, status="delivered")
        enriched = enricher.enrich_customers(customers, orders)
        assert enriched.iloc[0]["customer_segment"] == "new"

    def test_customer_segment_returning(self, enricher):
        customers = make_customers(n=1)
        orders = make_orders(n=3, customer_id=1, status="delivered")
        enriched = enricher.enrich_customers(customers, orders)
        assert enriched.iloc[0]["customer_segment"] == "returning"

    def test_customer_segment_loyal(self, enricher):
        customers = make_customers(n=1)
        orders = make_orders(n=6, customer_id=1, status="delivered")
        enriched = enricher.enrich_customers(customers, orders)
        assert enriched.iloc[0]["customer_segment"] == "loyal"

    def test_no_orders_gives_zero_count(self, enricher):
        customers = make_customers(n=2)
        enriched = enricher.enrich_customers(customers, pd.DataFrame())
        assert (enriched["order_count"] == 0).all()


class TestEnrichProducts:
    def test_price_tier_budget(self, enricher):
        df = make_products()
        enriched = enricher.enrich_products(df)
        assert enriched.loc[0, "price_tier"] == "budget"   # price=10

    def test_price_tier_mid(self, enricher):
        df = make_products()
        enriched = enricher.enrich_products(df)
        assert enriched.loc[1, "price_tier"] == "mid"      # price=50

    def test_price_tier_premium(self, enricher):
        df = make_products()
        enriched = enricher.enrich_products(df)
        assert enriched.loc[2, "price_tier"] == "premium"  # price=120

    def test_margin_tier_high(self, enricher):
        df = make_products()
        enriched = enricher.enrich_products(df)
        assert enriched.loc[0, "margin_tier"] == "high"    # margin=70%

    def test_empty_returns_empty(self, enricher):
        result = enricher.enrich_products(pd.DataFrame())
        assert result.empty
