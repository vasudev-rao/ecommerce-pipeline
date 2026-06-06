"""
Airflow DAG — daily e-commerce pipeline.
Runs at 02:00 UTC, processes previous day's data.
"""

from __future__ import annotations

from datetime import date, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(hours=2),
}

with DAG(
    dag_id="ecommerce_daily_pipeline",
    description="Daily e-commerce ETL: Postgres → S3 → BigQuery → dbt",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",
    start_date=days_ago(1),
    catchup=True,
    max_active_runs=1,
    tags=["ecommerce", "daily", "batch"],
    doc_md="""
## E-Commerce Daily Pipeline

Extracts orders, customers, products from PostgreSQL →
cleans and enriches → loads to BigQuery → runs dbt models.

### Backfill
```bash
airflow dags backfill ecommerce_daily_pipeline \\
    --start-date 2024-01-01 --end-date 2024-01-31
```
    """,
) as dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end")

    @task(task_id="extract")
    def extract(execution_date=None, **context):
        from src.config_loader import get_config
        from src.logger import configure_logging, get_logger
        from src.helpers import generate_run_id
        from etl.extract.postgres_extract import PostgresExtractor
        from etl.load.s3_load import S3Loader
        import pandas as pd

        cfg = get_config()
        configure_logging(cfg.observability.log_level, cfg.observability.log_format)
        log = get_logger(__name__)

        run_date = execution_date.date() if execution_date else date.today() - timedelta(days=1)
        run_id = generate_run_id("batch", run_date)

        extractor = PostgresExtractor()
        raw = extractor.extract_all(run_date, run_id)
        extractor.close()

        # Save raw data to S3/local for downstream tasks
        s3 = S3Loader()
        for table, df in raw.items():
            s3.save(df, table=table, run_date=run_date, stage="raw", run_id=run_id)

        total = sum(len(df) for df in raw.values())
        log.info("Extract task complete", rows=total, run_id=run_id)
        return {"run_id": run_id, "run_date": run_date.isoformat(), "rows_extracted": total}

    @task(task_id="clean_and_enrich")
    def clean_and_enrich(extract_result: dict, **context):
        from datetime import date as date_type
        from src.config_loader import get_config
        from src.logger import configure_logging, get_logger
        from etl.transform.clean import DataCleaner
        from etl.transform.enrich import DataEnricher
        from etl.load.s3_load import S3Loader

        cfg = get_config()
        configure_logging(cfg.observability.log_level, cfg.observability.log_format)
        log = get_logger(__name__)

        run_id   = extract_result["run_id"]
        run_date = date_type.fromisoformat(extract_result["run_date"])
        s3 = S3Loader()

        # Load raw from previous task
        raw = {t: s3.load(t, run_date, stage="raw")
               for t in ("orders", "order_items", "customers", "products")}

        cleaner  = DataCleaner()
        enricher = DataEnricher()

        clean_orders,    _ = cleaner.clean_orders(raw["orders"], run_id)
        clean_items,     _ = cleaner.clean_order_items(raw["order_items"], run_id)
        clean_customers, _ = cleaner.clean_customers(raw["customers"], run_id)
        clean_products,  _ = cleaner.clean_products(raw["products"], run_id)

        enriched_orders    = enricher.enrich_orders(clean_orders)
        enriched_customers = enricher.enrich_customers(clean_customers, clean_orders)
        enriched_products  = enricher.enrich_products(clean_products)

        for table, df in [
            ("orders", enriched_orders), ("order_items", clean_items),
            ("customers", enriched_customers), ("products", enriched_products),
        ]:
            s3.save(df, table=table, run_date=run_date, stage="processed", run_id=run_id)

        total = len(enriched_orders) + len(clean_items) + len(enriched_customers) + len(enriched_products)
        log.info("Clean+enrich task complete", rows=total, run_id=run_id)
        return {**extract_result, "rows_processed": total}

    @task(task_id="load_bigquery")
    def load_bigquery(transform_result: dict, **context):
        from datetime import date as date_type
        from src.config_loader import get_config
        from src.logger import configure_logging, get_logger
        from etl.load.bigquery_load import BigQueryLoader
        from etl.load.s3_load import S3Loader

        cfg = get_config()
        configure_logging(cfg.observability.log_level, cfg.observability.log_format)
        log = get_logger(__name__)

        run_id   = transform_result["run_id"]
        run_date = date_type.fromisoformat(transform_result["run_date"])
        s3 = S3Loader()

        processed = {t: s3.load(t, run_date, stage="processed")
                     for t in ("orders", "order_items", "customers", "products")}

        bq = BigQueryLoader()
        loaded = bq.load_all(processed, run_id=run_id)

        total = sum(loaded.values())
        log.info("BigQuery load complete", rows_loaded=total, run_id=run_id)
        return {**transform_result, "rows_loaded": total}

    @task(task_id="run_dbt")
    def run_dbt(load_result: dict, **context):
        import subprocess
        from pathlib import Path
        from src.logger import get_logger
        log = get_logger(__name__)

        dbt_dir = Path(__file__).parents[1] / "dbt"
        result = subprocess.run(
            ["dbt", "run", "--profiles-dir", str(dbt_dir), "--project-dir", str(dbt_dir)],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"dbt failed: {result.stderr[-500:]}")
        log.info("dbt run complete", run_id=load_result["run_id"])
        return {**load_result, "dbt_status": "success"}

    @task(task_id="notify")
    def notify(result: dict, **context):
        from src.config_loader import get_config
        from src.helpers import send_slack_alert
        cfg = get_config()
        msg = (
            f":white_check_mark: *E-Commerce pipeline succeeded*\n"
            f"run_id: `{result['run_id']}`\n"
            f"date: `{result['run_date']}`\n"
            f"rows loaded: `{result.get('rows_loaded', 0):,}`"
        )
        send_slack_alert(msg, cfg.observability.slack_webhook_url)

    # Wire
    extract_result    = extract()
    transform_result  = clean_and_enrich(extract_result)
    load_result       = load_bigquery(transform_result)
    dbt_result        = run_dbt(load_result)
    notify_result     = notify(dbt_result)

    start >> extract_result
    notify_result >> end
