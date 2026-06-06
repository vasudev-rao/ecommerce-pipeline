"""
PostgreSQL extractor — pulls orders, customers, products using watermarks.

Uses updated_at watermark so only changed rows are fetched on each run.
First run extracts the full day specified by run_date.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

from src.config_loader import get_config
from src.helpers import generate_run_id
from src.logger import get_logger

logger = get_logger(__name__)


class PostgresExtractor:
    """Incremental extractor for the e-commerce source database."""

    WATERMARK_DIR = Path("/tmp/ecommerce-pipeline/watermarks")

    def __init__(self) -> None:
        cfg = get_config()
        self._engine = create_engine(
            cfg.database.url,
            pool_size=cfg.database.pool_size,
            pool_pre_ping=True,
        )
        self.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public ──────────────────────────────────────────────────────────────

    def extract_all(self, run_date: date, run_id: str) -> dict[str, pd.DataFrame]:
        """
        Extract all source tables for a given run date.

        Returns:
            Dict with keys: orders, order_items, customers, products
        """
        logger.info("Starting extraction", run_date=run_date.isoformat(), run_id=run_id)

        result = {
            "orders":      self.extract_orders(run_date),
            "order_items": self.extract_order_items(run_date),
            "customers":   self.extract_customers(run_date),
            "products":    self.extract_products(run_date),
        }

        for table, df in result.items():
            logger.info("Table extracted", table=table, rows=len(df), run_id=run_id)

        return result

    def extract_orders(self, run_date: date) -> pd.DataFrame:
        watermark = self._load_watermark("orders")
        if watermark:
            query = """
                SELECT o.*, c.country as customer_country
                FROM orders o
                JOIN customers c ON o.customer_id = c.customer_id
                WHERE o.updated_at > :watermark
                ORDER BY o.updated_at ASC
            """
            params = {"watermark": watermark}
        else:
            query = """
                SELECT o.*, c.country as customer_country
                FROM orders o
                JOIN customers c ON o.customer_id = c.customer_id
                WHERE o.order_date = :run_date
                ORDER BY o.updated_at ASC
            """
            params = {"run_date": run_date}

        df = self._read_sql(query, params)
        if not df.empty and "updated_at" in df.columns:
            max_ts = pd.to_datetime(df["updated_at"]).max()
            self._save_watermark("orders", max_ts.to_pydatetime())
        return df

    def extract_order_items(self, run_date: date) -> pd.DataFrame:
        query = """
            SELECT oi.*
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.order_date = :run_date
        """
        return self._read_sql(query, {"run_date": run_date})

    def extract_customers(self, run_date: date) -> pd.DataFrame:
        watermark = self._load_watermark("customers")
        if watermark:
            query = "SELECT * FROM customers WHERE updated_at > :watermark ORDER BY updated_at"
            params: dict[str, Any] = {"watermark": watermark}
        else:
            query = "SELECT * FROM customers WHERE signup_date <= :run_date ORDER BY created_at"
            params = {"run_date": run_date}

        df = self._read_sql(query, params)
        if not df.empty and "updated_at" in df.columns:
            max_ts = pd.to_datetime(df["updated_at"]).max()
            self._save_watermark("customers", max_ts.to_pydatetime())
        return df

    def extract_products(self, run_date: date) -> pd.DataFrame:
        query = "SELECT * FROM products WHERE is_active = TRUE ORDER BY product_id"
        return self._read_sql(query, {})

    # ── Internal ─────────────────────────────────────────────────────────────

    def _read_sql(self, query: str, params: dict[str, Any]) -> pd.DataFrame:
        with self._engine.connect() as conn:
            return pd.read_sql(text(query), conn, params=params)

    def _watermark_path(self, table: str) -> Path:
        return self.WATERMARK_DIR / f"{table}.json"

    def _load_watermark(self, table: str) -> datetime | None:
        path = self._watermark_path(table)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return datetime.fromisoformat(data["watermark"])

    def _save_watermark(self, table: str, ts: datetime) -> None:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        self._watermark_path(table).write_text(
            json.dumps({"watermark": ts.isoformat()})
        )

    def close(self) -> None:
        self._engine.dispose()
