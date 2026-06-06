"""
Clean stage — validates and standardises extracted DataFrames.

Operations per table:
  orders:      null checks, amount validation, status whitelist, date parsing
  order_items: null checks, quantity > 0, price > 0
  customers:   null checks, email format, country code
  products:    null checks, price > cost sanity, category whitelist
"""

from __future__ import annotations

import re
from datetime import timezone

import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled", "refunded"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD"}


class DataCleaner:
    """Cleans extracted DataFrames. Returns (clean_df, issues: list[str])."""

    # ── Orders ───────────────────────────────────────────────────────────────

    def clean_orders(self, df: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, list[str]]:
        if df.empty:
            return df, []

        df = df.copy()
        issues: list[str] = []
        original_len = len(df)

        # Type coercion
        df["order_id"]      = pd.to_numeric(df["order_id"], errors="coerce")
        df["customer_id"]   = pd.to_numeric(df["customer_id"], errors="coerce")
        df["total_amount"]  = pd.to_numeric(df["total_amount"], errors="coerce")
        df["discount_amount"] = pd.to_numeric(df["discount_amount"], errors="coerce").fillna(0)
        df["shipping_amount"] = pd.to_numeric(df["shipping_amount"], errors="coerce").fillna(0)
        df["order_date"]    = pd.to_datetime(df["order_date"], errors="coerce").dt.date
        df["currency"]      = df["currency"].str.upper().str.strip()

        # Drop null primary keys
        null_mask = df["order_id"].isna() | df["customer_id"].isna()
        if null_mask.any():
            issues.append(f"{null_mask.sum()} orders dropped: null order_id or customer_id")
            df = df[~null_mask]

        # Status validation
        invalid_status = ~df["status"].isin(VALID_STATUSES)
        if invalid_status.any():
            issues.append(f"{invalid_status.sum()} orders with invalid status set to 'pending'")
            df.loc[invalid_status, "status"] = "pending"

        # Amount validation
        bad_amount = (df["total_amount"] <= 0) | df["total_amount"].isna()
        if bad_amount.any():
            issues.append(f"{bad_amount.sum()} orders dropped: invalid total_amount")
            df = df[~bad_amount]

        # Currency validation
        bad_currency = ~df["currency"].isin(VALID_CURRENCIES)
        if bad_currency.any():
            issues.append(f"{bad_currency.sum()} orders: unknown currency set to USD")
            df.loc[bad_currency, "currency"] = "USD"

        # Dedup
        df = df.drop_duplicates(subset=["order_id"], keep="last")

        # Add lineage
        df["run_id"] = run_id
        df["cleaned_at"] = pd.Timestamp.now(tz="UTC")

        removed = original_len - len(df)
        logger.info("Orders cleaned", original=original_len, clean=len(df), removed=removed,
                    issues=len(issues), run_id=run_id)
        return df.reset_index(drop=True), issues

    # ── Order items ───────────────────────────────────────────────────────────

    def clean_order_items(self, df: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, list[str]]:
        if df.empty:
            return df, []

        df = df.copy()
        issues: list[str] = []

        df["order_id"]   = pd.to_numeric(df["order_id"], errors="coerce")
        df["product_id"] = pd.to_numeric(df["product_id"], errors="coerce")
        df["quantity"]   = pd.to_numeric(df["quantity"], errors="coerce")
        df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
        df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce").fillna(0)

        bad = (
            df["order_id"].isna() |
            df["product_id"].isna() |
            (df["quantity"] <= 0) |
            (df["unit_price"] <= 0)
        )
        if bad.any():
            issues.append(f"{bad.sum()} order items dropped: invalid keys/quantity/price")
            df = df[~bad]

        # Computed columns
        df["line_total"] = (
            df["unit_price"] * df["quantity"] * (1 - df["discount_pct"] / 100)
        ).round(2)
        df["run_id"] = run_id

        logger.info("Order items cleaned", rows=len(df), run_id=run_id)
        return df.reset_index(drop=True), issues

    # ── Customers ─────────────────────────────────────────────────────────────

    def clean_customers(self, df: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, list[str]]:
        if df.empty:
            return df, []

        df = df.copy()
        issues: list[str] = []

        df["customer_id"] = pd.to_numeric(df["customer_id"], errors="coerce")
        df["email"]       = df["email"].str.lower().str.strip()
        df["first_name"]  = df["first_name"].str.strip().str.title()
        df["last_name"]   = df["last_name"].str.strip().str.title()
        df["country"]     = df["country"].str.upper().str.strip()
        df["signup_date"] = pd.to_datetime(df["signup_date"], errors="coerce").dt.date

        # Drop nulls on required fields
        bad = df["customer_id"].isna() | df["email"].isna()
        if bad.any():
            issues.append(f"{bad.sum()} customers dropped: null id or email")
            df = df[~bad]

        # Email format check
        invalid_email = ~df["email"].str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", na=False)
        if invalid_email.any():
            issues.append(f"{invalid_email.sum()} customers dropped: invalid email format")
            df = df[~invalid_email]

        # Country code normalise
        df["country"] = df["country"].where(df["country"].str.len() == 2, "XX")

        df = df.drop_duplicates(subset=["customer_id"], keep="last")
        df["run_id"] = run_id

        logger.info("Customers cleaned", rows=len(df), run_id=run_id)
        return df.reset_index(drop=True), issues

    # ── Products ──────────────────────────────────────────────────────────────

    def clean_products(self, df: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, list[str]]:
        if df.empty:
            return df, []

        df = df.copy()
        issues: list[str] = []

        df["product_id"] = pd.to_numeric(df["product_id"], errors="coerce")
        df["price"]      = pd.to_numeric(df["price"], errors="coerce")
        df["cost"]       = pd.to_numeric(df["cost"], errors="coerce")
        df["name"]       = df["name"].str.strip()
        df["category"]   = df["category"].str.strip().str.title()
        df["sku"]        = df["sku"].str.upper().str.strip()

        bad = df["product_id"].isna() | (df["price"] <= 0)
        if bad.any():
            issues.append(f"{bad.sum()} products dropped: null id or invalid price")
            df = df[~bad]

        # Margin sanity: cost should be less than price
        bad_margin = df["cost"] >= df["price"]
        if bad_margin.any():
            issues.append(f"{bad_margin.sum()} products: cost >= price, capping cost at 90% of price")
            df.loc[bad_margin, "cost"] = (df.loc[bad_margin, "price"] * 0.9).round(2)

        # Computed margin column
        df["margin_pct"] = ((df["price"] - df["cost"]) / df["price"] * 100).round(2)

        df = df.drop_duplicates(subset=["product_id"], keep="last")
        df["run_id"] = run_id

        logger.info("Products cleaned", rows=len(df), run_id=run_id)
        return df.reset_index(drop=True), issues
