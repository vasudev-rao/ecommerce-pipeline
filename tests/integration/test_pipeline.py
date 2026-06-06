"""
Integration tests — full pipeline E2E with a real Postgres database.

Requires:
  ENV=test
  DB_HOST=localhost  DB_PORT=5432
  DB_USER=ecommerce_user  DB_PASSWORD=changeme  DB_NAME=ecommerce_db

Run:
  ENV=test pytest tests/integration/ -v --timeout=60
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pandas as pd
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("ENV", "development") not in ("test", "ci"),
        reason="Integration tests only run with ENV=test",
    ),
]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_engine():
    from sqlalchemy import create_engine, text
    from src.config_loader import get_config
    cfg = get_config()
    engine = create_engine(cfg.database.url, pool_pre_ping=True)

    with engine.connect() as conn:
        # Minimal test tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                country VARCHAR(2) NOT NULL DEFAULT 'US',
                city VARCHAR(100),
                signup_date DATE NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                product_id SERIAL PRIMARY KEY,
                sku VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                cost NUMERIC(10,2) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                total_amount NUMERIC(10,2) NOT NULL,
                discount_amount NUMERIC(10,2) DEFAULT 0,
                shipping_amount NUMERIC(10,2) DEFAULT 0,
                currency VARCHAR(3) DEFAULT 'USD',
                payment_method VARCHAR(50),
                order_date DATE NOT NULL,
                shipped_date DATE,
                delivered_date DATE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS order_items (
                item_id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price NUMERIC(10,2) NOT NULL,
                discount_pct NUMERIC(5,2) DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(text("TRUNCATE orders, order_items, customers, products RESTART IDENTITY CASCADE"))
        conn.commit()

    yield engine

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE orders, order_items, customers, products RESTART IDENTITY CASCADE"))
        conn.commit()
    engine.dispose()


@pytest.fixture(scope="session")
def seed_data(db_engine):
    """Insert minimal test data."""
    from sqlalchemy import text
    today = date.today()

    with db_engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO customers (email, first_name, last_name, country, signup_date)
            VALUES
                ('alice@test.com', 'Alice', 'Smith', 'US', :d),
                ('bob@test.com', 'Bob', 'Jones', 'GB', :d),
                ('carol@test.com', 'Carol', 'Brown', 'US', :d)
        """), {"d": today})

        conn.execute(text("""
            INSERT INTO products (sku, name, category, price, cost)
            VALUES
                ('SKU-001', 'Laptop Pro', 'Electronics', 999.99, 500.00),
                ('SKU-002', 'Blue Jeans', 'Clothing', 59.99, 20.00),
                ('SKU-003', 'Coffee Beans', 'Food', 19.99, 5.00)
        """))

        conn.execute(text("""
            INSERT INTO orders
                (customer_id, status, total_amount, discount_amount, order_date, delivered_date)
            VALUES
                (1, 'delivered', 999.99, 0, :d, :d),
                (2, 'delivered', 59.99,  5, :d, :d),
                (1, 'cancelled', 19.99,  0, :d, NULL),
                (3, 'shipped',   199.99, 10, :d, NULL)
        """), {"d": today})

        conn.execute(text("""
            INSERT INTO order_items (order_id, product_id, quantity, unit_price)
            VALUES (1,1,1,999.99), (2,2,1,59.99), (3,3,2,9.99), (4,1,1,199.99)
        """))
        conn.commit()

    return {"run_date": today}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPostgresExtraction:
    def test_extracts_orders(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PostgresExtractor()
            extractor.WATERMARK_DIR = type(extractor.WATERMARK_DIR)(tmpdir)
            extractor.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
            df = extractor.extract_orders(seed_data["run_date"])
            extractor.close()
        assert len(df) >= 4
        assert "order_id" in df.columns
        assert "customer_id" in df.columns

    def test_extracts_customers(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PostgresExtractor()
            extractor.WATERMARK_DIR = type(extractor.WATERMARK_DIR)(tmpdir)
            extractor.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
            df = extractor.extract_customers(seed_data["run_date"])
            extractor.close()
        assert len(df) == 3
        assert set(["alice@test.com", "bob@test.com", "carol@test.com"]).issubset(
            set(df["email"].tolist())
        )

    def test_extracts_products(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        extractor = PostgresExtractor()
        df = extractor.extract_products(seed_data["run_date"])
        extractor.close()
        assert len(df) == 3
        assert "price" in df.columns


class TestCleanIntegration:
    def test_clean_extracted_orders(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        from etl.transform.clean import DataCleaner
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PostgresExtractor()
            extractor.WATERMARK_DIR = type(extractor.WATERMARK_DIR)(tmpdir)
            extractor.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
            orders_df = extractor.extract_orders(seed_data["run_date"])
            extractor.close()

        cleaner = DataCleaner()
        clean_df, issues = cleaner.clean_orders(orders_df, "integration-test-001")

        assert not clean_df.empty
        assert "run_id" in clean_df.columns
        assert (clean_df["run_id"] == "integration-test-001").all()
        assert clean_df["order_id"].nunique() == len(clean_df)

    def test_no_negative_amounts_after_clean(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        from etl.transform.clean import DataCleaner
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PostgresExtractor()
            extractor.WATERMARK_DIR = type(extractor.WATERMARK_DIR)(tmpdir)
            extractor.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
            orders_df = extractor.extract_orders(seed_data["run_date"])
            extractor.close()

        cleaner = DataCleaner()
        clean_df, _ = cleaner.clean_orders(orders_df, "test-run")
        assert (clean_df["total_amount"] > 0).all()


class TestEnrichIntegration:
    def test_customer_segments_assigned(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        from etl.transform.clean import DataCleaner
        from etl.transform.enrich import DataEnricher
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PostgresExtractor()
            extractor.WATERMARK_DIR = type(extractor.WATERMARK_DIR)(tmpdir)
            extractor.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
            raw = extractor.extract_all(seed_data["run_date"], "int-test")
            extractor.close()

        cleaner = DataCleaner()
        clean_orders, _ = cleaner.clean_orders(raw["orders"], "int-test")
        clean_customers, _ = cleaner.clean_customers(raw["customers"], "int-test")

        enricher = DataEnricher()
        enriched = enricher.enrich_customers(clean_customers, clean_orders)

        assert "customer_segment" in enriched.columns
        assert enriched["customer_segment"].isin(["new", "returning", "loyal"]).all()
        assert (enriched["order_count"] >= 0).all()

    def test_order_time_dimensions_present(self, db_engine, seed_data):
        from etl.extract.postgres_extract import PostgresExtractor
        from etl.transform.clean import DataCleaner
        from etl.transform.enrich import DataEnricher
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            extractor = PostgresExtractor()
            extractor.WATERMARK_DIR = type(extractor.WATERMARK_DIR)(tmpdir)
            extractor.WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
            orders_df = extractor.extract_orders(seed_data["run_date"])
            extractor.close()

        cleaner = DataCleaner()
        clean_df, _ = cleaner.clean_orders(orders_df, "int-test")
        enricher = DataEnricher()
        enriched = enricher.enrich_orders(clean_df)

        for col in ["day_of_week", "month", "quarter", "year", "is_weekend"]:
            assert col in enriched.columns
