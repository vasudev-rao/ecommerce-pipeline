# ecommerce-pipeline

> Daily batch pipeline: PostgreSQL → pandas ETL → BigQuery → dbt → Metabase dashboard.
> Processes 50,000+ orders/day. Fully runnable on a laptop at zero cost.

---

## What it does

1. **Extracts** orders, customers, products from a PostgreSQL source DB (watermark-based — only new/changed rows)
2. **Cleans** the data — null handling, type casting, deduplication, bad-row logging
3. **Enriches** — customer segments (new/returning/loyal), product price tiers, revenue metrics
4. **Loads** to BigQuery as parquet (S3 or local in dev)
5. **Transforms** with dbt — staging views + mart tables
6. **Visualises** in Metabase — revenue, retention, top products

---

## Quickstart (5 minutes)

### Prerequisites
- Python 3.11+
- Docker + Docker Compose
- Make

### 1. Install

```bash
git clone https://github.com/vasudevarao/ecommerce-pipeline.git
cd ecommerce-pipeline
make install-dev
cp .env.example .env
```

### 2. Start services

```bash
make docker-up
# Airflow UI  → http://localhost:8080  (admin/admin)
# Metabase    → http://localhost:3000
# Postgres    → localhost:5432
```

### 3. Seed data

```bash
make seed          # 50,000 orders (takes ~2 min)
make seed-small    # 1,000 orders  (takes ~5 sec)
```

### 4. Run the pipeline

```bash
# Run for yesterday (default)
make run

# Run for a specific date
make run DATE=2024-01-15

# Or directly
python -m pipeline.batch_pipeline --date 2024-01-15
```

### 5. Run tests

```bash
make test-unit     # Fast — no DB needed
make test-int      # Requires Docker Postgres running
make coverage      # Unit tests + HTML coverage report
```

---

## Project structure

```
ecommerce-pipeline/
├── config/             YAML config (base.yaml)
├── dags/               Airflow DAGs
│   ├── daily_pipeline.py    Daily ETL at 02:00 UTC
│   └── backfill.py          Manual date-range reprocessing
├── dbt/                dbt SQL transform models
│   └── models/
│       ├── staging/    stg_orders, stg_customers, stg_products
│       └── mart/       daily_revenue, customer_retention, top_products
├── docker/             docker-compose.yml + Dockerfile
├── etl/
│   ├── extract/        postgres_extract.py
│   ├── transform/      clean.py · enrich.py
│   └── load/           bigquery_load.py · s3_load.py
├── pipeline/           batch_pipeline.py (orchestration)
├── scripts/            setup_source_db.sql · seed_data.py
├── src/                config_loader · logger · helpers
└── tests/              25+ unit tests · integration tests
```

---

## Tech stack

| Layer | Tool |
|---|---|
| Source DB | PostgreSQL 15 |
| ETL | Python 3.11 + pandas |
| Orchestration | Apache Airflow 2.8 |
| Storage | S3 / local parquet |
| Warehouse | BigQuery (1 TB free/month) |
| Transforms | dbt Core |
| Dashboard | Metabase |
| CI/CD | GitHub Actions (3-stage: lint → unit → integration) |

**Total infrastructure cost: $0/month** on BigQuery free tier + AWS free tier EC2/S3.

---

## Local vs cloud

| Component | Local (dev) | Cloud (prod) |
|---|---|---|
| Storage | `/tmp/ecommerce-pipeline/data/` | S3 bucket |
| Warehouse | BigQuery free tier | BigQuery |
| Airflow | Docker Compose | EC2 t3.micro |
| Source DB | Docker Compose | RDS t3.micro (free tier) |

No code changes needed — set env vars to switch between local and cloud.

---

## Backfill

```bash
# Via Airflow UI trigger, or:
airflow dags trigger ecommerce_backfill \
    --conf '{"start_date": "2024-01-01", "end_date": "2024-01-31"}'
```

---

## Design decisions

**Why pandas over Spark?** At 50k orders/day, pandas is 10x simpler and runs on a single
EC2 t3.micro. Spark adds complexity and cost without benefit at this scale.

**Why BigQuery free tier?** 1 TB of queries/month free forever. No server to manage.
DuckDB is also embedded in the pipeline as a zero-config local alternative.

**Why watermark over full extract?** A full daily extract of 2 years of orders would take
minutes and hammer the source DB. Watermark extraction takes seconds and is invisible to
production traffic.

**Why dbt on top of raw BigQuery tables?** All business logic is in SQL, version-controlled,
and testable with `dbt test`. Analysts can read and modify mart definitions without touching
Python code.

---

## Author

Vasudev A Rao — Senior Data Engineer
[vasudevarao.com](https://vasudevarao.com) · [GitHub](https://github.com/vasudevarao)
