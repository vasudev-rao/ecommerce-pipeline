"""
Enrich stage — adds derived business columns before loading.

Enrichments:
  orders:    revenue_net, is_high_value, day_of_week, week_of_year
  customers: customer_segment (new/returning/loyal), lifetime_value
  products:  price_tier (budget/mid/premium), margin_tier
"""

from __future__ import annotations

import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)


class DataEnricher:

    # ── Orders ────────────────────────────────────────────────────────────────

    def enrich_orders(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        if orders_df.empty:
            return orders_df

        df = orders_df.copy()

        # Revenue net of discounts and shipping
        df["revenue_net"] = (
            df["total_amount"] - df["discount_amount"]
        ).round(2)

        # High-value order flag (above $200)
        df["is_high_value"] = df["total_amount"] > 200.0

        # Time dimensions
        order_dates = pd.to_datetime(df["order_date"])
        df["day_of_week"]  = order_dates.dt.day_name()
        df["week_of_year"] = order_dates.dt.isocalendar().week.astype(int)
        df["month"]        = order_dates.dt.month
        df["quarter"]      = order_dates.dt.quarter
        df["year"]         = order_dates.dt.year
        df["is_weekend"]   = order_dates.dt.dayofweek >= 5

        logger.info("Orders enriched", rows=len(df))
        return df

    # ── Customers ─────────────────────────────────────────────────────────────

    def enrich_customers(
        self,
        customers_df: pd.DataFrame,
        orders_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Add customer_segment and order_count based on order history.
        Segment rules:
          new       — 0 orders or signed up in last 30 days
          returning — 2–4 lifetime orders
          loyal     — 5+ lifetime orders
        """
        if customers_df.empty:
            return customers_df

        df = customers_df.copy()

        # Count completed orders per customer
        if not orders_df.empty:
            completed = orders_df[orders_df["status"] == "delivered"]
            order_counts = (
                completed.groupby("customer_id")["order_id"].count().reset_index()
                .rename(columns={"order_id": "order_count"})
            )
            revenue = (
                completed.groupby("customer_id")["total_amount"].sum().reset_index()
                .rename(columns={"total_amount": "lifetime_value"})
            )
            df = df.merge(order_counts, on="customer_id", how="left")
            df = df.merge(revenue, on="customer_id", how="left")
        else:
            df["order_count"]    = 0
            df["lifetime_value"] = 0.0

        df["order_count"]    = df["order_count"].fillna(0).astype(int)
        df["lifetime_value"] = df["lifetime_value"].fillna(0.0).round(2)

        # Segment assignment
        df["customer_segment"] = "new"
        df.loc[df["order_count"].between(2, 4), "customer_segment"] = "returning"
        df.loc[df["order_count"] >= 5,          "customer_segment"] = "loyal"

        # Days since signup
        df["days_since_signup"] = (
            pd.Timestamp.now(tz="UTC").date()
            - pd.to_datetime(df["signup_date"]).dt.date
        ).apply(lambda x: x.days if hasattr(x, "days") else 0)

        logger.info("Customers enriched", rows=len(df))
        return df

    # ── Products ──────────────────────────────────────────────────────────────

    def enrich_products(self, products_df: pd.DataFrame) -> pd.DataFrame:
        if products_df.empty:
            return products_df

        df = products_df.copy()

        # Price tier
        conditions = [
            df["price"] < 30,
            df["price"].between(30, 100),
            df["price"] > 100,
        ]
        df["price_tier"] = "mid"
        df.loc[conditions[0], "price_tier"] = "budget"
        df.loc[conditions[2], "price_tier"] = "premium"

        # Margin tier
        df["margin_tier"] = "standard"
        df.loc[df["margin_pct"] >= 60, "margin_tier"] = "high"
        df.loc[df["margin_pct"] < 30,  "margin_tier"] = "low"

        logger.info("Products enriched", rows=len(df))
        return df
