"""
Backfill DAG — manually trigger to reprocess a date range.

Trigger:
    airflow dags trigger ecommerce_backfill \\
        --conf '{"start_date": "2024-01-01", "end_date": "2024-01-31"}'
"""

from __future__ import annotations

from datetime import timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago

with DAG(
    dag_id="ecommerce_backfill",
    description="Manual backfill for date ranges",
    default_args={"owner": "data-engineering", "retries": 1},
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["ecommerce", "backfill"],
) as dag:

    start = EmptyOperator(task_id="start")
    end   = EmptyOperator(task_id="end", trigger_rule="all_done")

    @task(task_id="validate_and_run")
    def validate_and_run(**context):
        from datetime import date as date_type
        from src.config_loader import get_config
        from src.logger import configure_logging, get_logger
        from src.helpers import date_range, parse_date
        from pipeline.batch_pipeline import BatchPipeline

        cfg = get_config()
        configure_logging(cfg.observability.log_level, cfg.observability.log_format)
        log = get_logger(__name__)

        params     = context.get("params") or context.get("dag_run").conf or {}
        start_date = parse_date(params.get("start_date", str(date_type.today())))
        end_date   = parse_date(params.get("end_date",   str(date_type.today())))

        if (end_date - start_date).days > 90:
            raise ValueError("Date range exceeds 90 days. Split into smaller backfills.")

        dates = list(date_range(start_date, end_date))
        log.info("Backfill starting", start=start_date.isoformat(),
                 end=end_date.isoformat(), days=len(dates))

        pipeline = BatchPipeline()
        results = {"success": 0, "failed": 0, "failed_dates": []}

        for d in dates:
            try:
                pipeline.run(run_date=d)
                results["success"] += 1
            except Exception as exc:
                results["failed"] += 1
                results["failed_dates"].append(d.isoformat())
                log.error("Backfill date failed", date=d.isoformat(), error=str(exc))

        log.info("Backfill complete", **results)
        return results

    result = validate_and_run()
    start >> result >> end
