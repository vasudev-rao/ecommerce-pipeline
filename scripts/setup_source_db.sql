-- setup_source_db.sql
-- Creates the source e-commerce transactional tables.
-- Run once against the source PostgreSQL DB before seeding data.
-- psql -U ecommerce_user -d ecommerce_db -f scripts/setup_source_db.sql

CREATE TABLE IF NOT EXISTS customers (
    customer_id     SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    country         VARCHAR(2)   NOT NULL DEFAULT 'US',
    city            VARCHAR(100),
    signup_date     DATE         NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    sku             VARCHAR(50)  UNIQUE NOT NULL,
    name            VARCHAR(255) NOT NULL,
    category        VARCHAR(100) NOT NULL,
    subcategory     VARCHAR(100),
    price           NUMERIC(10,2) NOT NULL,
    cost            NUMERIC(10,2) NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER      NOT NULL REFERENCES customers(customer_id),
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','confirmed','shipped','delivered','cancelled','refunded')),
    total_amount    NUMERIC(10,2) NOT NULL,
    discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    shipping_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
    currency        VARCHAR(3)   NOT NULL DEFAULT 'USD',
    payment_method  VARCHAR(50),
    order_date      DATE         NOT NULL,
    shipped_date    DATE,
    delivered_date  DATE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id         SERIAL PRIMARY KEY,
    order_id        INTEGER      NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER      NOT NULL REFERENCES products(product_id),
    quantity        INTEGER      NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10,2) NOT NULL,
    discount_pct    NUMERIC(5,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Index for incremental extraction (watermark on updated_at)
CREATE INDEX IF NOT EXISTS idx_orders_updated_at    ON orders(updated_at);
CREATE INDEX IF NOT EXISTS idx_customers_updated_at ON customers(updated_at);
CREATE INDEX IF NOT EXISTS idx_orders_order_date    ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

-- Pipeline tracking table (idempotency)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          VARCHAR(64)  PRIMARY KEY,
    pipeline        VARCHAR(64)  NOT NULL,
    run_date        DATE         NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'running',
    rows_extracted  INTEGER      DEFAULT 0,
    rows_loaded     INTEGER      DEFAULT 0,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    error_message   TEXT
);
