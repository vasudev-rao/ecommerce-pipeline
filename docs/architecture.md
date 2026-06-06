# Architecture — E-Commerce Sales Analytics Pipeline

## Overview

Daily batch pipeline that extracts sales data from a PostgreSQL source database,
cleans and enriches it, loads to BigQuery, and transforms it with dbt into
analytical mart tables powering a Metabase dashboard.

## Data flow

```
PostgreSQL (source)
  orders · customers · products · order_items
        │
        ▼ (watermark-based incremental extraction)
  Python ETL
  ├── extract  — pull changed rows since last watermark
  ├── clean    — validate, type cast, dedup, quarantine bad rows
  └── enrich   — add segments, tiers, revenue metrics
        │
        ▼
  S3 / Local parquet
  (raw landing + processed)
        │
        ▼
  BigQuery (raw dataset)
  orders · customers · products · order_items
        │
        ▼ (dbt run)
  BigQuery (staging)         BigQuery (mart)
  stg_orders                 daily_revenue
  stg_customers         →    customer_retention
  stg_products               top_products
        │
        ▼
  Metabase Dashboard
  Revenue · Retention · Top Products
```

## Directory structure

```
ecommerce-pipeline/
├── config/          YAML config (env vars override)
├── dags/            Airflow DAGs (daily + backfill)
├── dbt/             SQL transform models
├── docker/          Compose stack (Postgres + Airflow + Metabase)
├── etl/             Extract, transform, load modules
├── pipeline/        Orchestration entry point
├── scripts/         DB setup + seed data
├── src/             Shared utilities (config, logger, helpers)
└── tests/           Unit + integration tests
```

## Design decisions

**Watermark extraction** — only fetches rows where `updated_at > last_watermark`.
No full table scans. Watermark saved to disk and advances only on success.

**Clean returns (clean_df, issues)** — never silently drops data.
Every removed row is logged with a reason. Makes debugging straightforward.

**S3 as inter-task store** — DataFrames saved as parquet between Airflow tasks
instead of using XCom. No size limits, full auditability of intermediate data.

**BigQuery MERGE** — idempotent loads. Re-running the same date never creates
duplicate rows. Safe for backfills and retries.

**dbt on top of raw** — all business logic lives in SQL, version-controlled,
testable. Analysts can modify mart definitions without touching Python code.
