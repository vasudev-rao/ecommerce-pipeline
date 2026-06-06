"""
Batch pipeline — orchestrates the full daily ETL run.

Stages:
  1. Extract  — pull from PostgreSQL source DB
  2. Clean    — validate, type cast, dedup
  3. Enrich   — add business columns (segments, tiers, metrics)
  4. Load S3  — save parquet (raw landing + processed)
  5. Load BQ  — MERGE into BigQuery raw tables
  6. dbt run  — transform raw → staging → mart

Usage:
    python -m pipeline.batch_pipeline --date 2024-01-15
    python -m pipeline.batch_pipeline  # defaults to yesterday
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from src.config_loader import get_config
from src.helpers import generate_run_id, parse_date, send_slack_alert, yesterday
from src.logger import configure_logging, get_logger

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    run_id:       str
    run_date:     date
    status:       str = "pending"
    rows:         dict[str, int] = field(default_factory=dict)
    duration_sec: float = 0.0
    error:        str | None = None

    def log(self) -> None:
        logger.info(
            "Pipeline complete",
            run_id=self.run_id,
            run_date=self.run_date.isoformat(),
            status=self.status,
            rows=self.rows,
            duration_seconds=round(self.duration_sec, 1),
            error=self.error,
        )


class BatchPipeline:

    def run(self, run_date: date) -> PipelineResult:
        cfg = get_config()
        run_id = generate_run_id("batch", run_date)
        result = PipelineResult(run_id=run_id, run_date=run_date)
        start = time.perf_counter()

        logger.info(
            "Batch pipeline starting",
            run_id=run_id,
            run_date=run_date.isoformat(),
        )

        try:
            # ── Stage 1: Extract ───────────────────────────────────────────
            from etl.extract.postgres_extract import PostgresExtractor
            extractor = PostgresExtractor()
            raw = extractor.extract_all(run_date, run_id)
            extractor.close()

            result.rows["extracted"] = sum(len(df) for df in raw.values())
            logger.info("Extraction done", rows=result.rows["extracted"], run_id=run_id)

            # ── Stage 2: Clean ─────────────────────────────────────────────
            from etl.transform.clean import DataCleaner
            cleaner = DataCleaner()
            all_issues: list[str] = []

            clean_orders, issues = cleaner.clean_orders(raw["orders"], run_id)
            all_issues.extend(issues)
            clean_items, issues = cleaner.clean_order_items(raw["order_items"], run_id)
            all_issues.extend(issues)
            clean_customers, issues = cleaner.clean_customers(raw["customers"], run_id)
            all_issues.extend(issues)
            clean_products, issues = cleaner.clean_products(raw["products"], run_id)
            all_issues.extend(issues)

            if all_issues:
                logger.warning("Data quality issues found", issues=all_issues, run_id=run_id)

            result.rows["cleaned"] = (
                len(clean_orders) + len(clean_items) +
                len(clean_customers) + len(clean_products)
            )

            # ── Stage 3: Enrich ────────────────────────────────────────────
            from etl.transform.enrich import DataEnricher
            enricher = DataEnricher()
            enriched_orders    = enricher.enrich_orders(clean_orders)
            enriched_customers = enricher.enrich_customers(clean_customers, clean_orders)
            enriched_products  = enricher.enrich_products(clean_products)

            # ── Stage 4: Save to S3 (or local) ────────────────────────────
            from etl.load.s3_load import S3Loader
            s3 = S3Loader()
            for table, df in [
                ("orders",      enriched_orders),
                ("order_items", clean_items),
                ("customers",   enriched_customers),
                ("products",    enriched_products),
            ]:
                s3.save(df, table=table, run_date=run_date, stage="processed", run_id=run_id)

            # ── Stage 5: Load to BigQuery ──────────────────────────────────
            from etl.load.bigquery_load import BigQueryLoader
            bq = BigQueryLoader()
            loaded = bq.load_all(
                {
                    "orders":      enriched_orders,
                    "order_items": clean_items,
                    "customers":   enriched_customers,
                    "products":    enriched_products,
                },
                run_id=run_id,
            )
            result.rows["loaded_bq"] = sum(loaded.values())

            # ── Stage 6: dbt run ───────────────────────────────────────────
            self._run_dbt(run_id)

            # ── Success ────────────────────────────────────────────────────
            result.status = "success"
            result.duration_sec = time.perf_counter() - start
            result.log()

            if cfg.observability.slack_webhook_url:
                send_slack_alert(
                    f":white_check_mark: *E-Commerce pipeline succeeded*\n"
                    f"run_id: `{run_id}`\n"
                    f"date: `{run_date}`\n"
                    f"rows loaded: `{result.rows.get('loaded_bq', 0):,}`",
                    cfg.observability.slack_webhook_url,
                )

        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.duration_sec = time.perf_counter() - start
            result.log()

            logger.error(
                "Pipeline FAILED",
                run_id=run_id,
                error=str(exc),
                exc_info=True,
            )
            if cfg.observability.slack_webhook_url:
                send_slack_alert(
                    f":rotating_light: *E-Commerce pipeline FAILED*\n"
                    f"run_id: `{run_id}`\ndate: `{run_date}`\nerror: `{str(exc)[:200]}`",
                    cfg.observability.slack_webhook_url,
                )
            raise

        return result

    def _run_dbt(self, run_id: str) -> None:
        """Run dbt models after loading raw tables."""
        dbt_dir = Path(__file__).parents[1] / "dbt"
        if not dbt_dir.exists():
            logger.warning("dbt directory not found — skipping dbt run")
            return

        try:
            result = subprocess.run(
                ["dbt", "run", "--profiles-dir", str(dbt_dir), "--project-dir", str(dbt_dir)],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                logger.error("dbt run failed", stderr=result.stderr[-2000:])
                raise RuntimeError(f"dbt run failed: {result.stderr[-500:]}")
            logger.info("dbt run complete", run_id=run_id)
        except FileNotFoundError:
            logger.warning("dbt not installed — skipping. Install with: pip install dbt-bigquery")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the e-commerce batch pipeline.")
    parser.add_argument(
        "--date", type=str, default=None,
        help="Run date YYYY-MM-DD (default: yesterday)"
    )
    args = parser.parse_args()

    cfg = get_config()
    configure_logging(cfg.observability.log_level, cfg.observability.log_format)

    run_date = parse_date(args.date) if args.date else yesterday()

    pipeline = BatchPipeline()
    result = pipeline.run(run_date=run_date)
    sys.exit(0 if result.status == "success" else 1)


if __name__ == "__main__":
    main()
