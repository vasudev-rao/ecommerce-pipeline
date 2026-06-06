"""
BigQuery loader — idempotent load using MERGE or WRITE_TRUNCATE.

Each table is loaded with a different strategy:
  orders, order_items — MERGE on primary key (safe re-runs)
  customers, products — WRITE_TRUNCATE on daily snapshot (always fresh)

Requires: pip install google-cloud-bigquery db-dtypes
"""

from __future__ import annotations

import pandas as pd

from src.config_loader import get_config
from src.logger import get_logger

logger = get_logger(__name__)


class BigQueryLoader:
    """Loads DataFrames into BigQuery with idempotency."""

    def __init__(self) -> None:
        self._cfg = get_config().bigquery
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from google.cloud import bigquery  # type: ignore
                self._client = bigquery.Client(project=self._cfg.project_id)
            except ImportError:
                raise RuntimeError(
                    "google-cloud-bigquery not installed. "
                    "Run: pip install google-cloud-bigquery db-dtypes"
                )
        return self._client

    # ── Public ──────────────────────────────────────────────────────────────

    def load_all(
        self,
        tables: dict[str, pd.DataFrame],
        run_id: str,
    ) -> dict[str, int]:
        """
        Load all tables to BigQuery.

        Args:
            tables:  Dict of table_name → DataFrame.
            run_id:  Pipeline run ID for logging.

        Returns:
            Dict of table_name → rows loaded.
        """
        results: dict[str, int] = {}
        for table_name, df in tables.items():
            if df.empty:
                logger.info("Skipping empty table", table=table_name, run_id=run_id)
                results[table_name] = 0
                continue
            rows = self._load_table(table_name, df, run_id)
            results[table_name] = rows
        return results

    # ── Internal ─────────────────────────────────────────────────────────────

    def _load_table(self, table_name: str, df: pd.DataFrame, run_id: str) -> int:
        """Route to the appropriate load strategy per table."""
        target = f"{self._cfg.project_id}.{self._cfg.dataset_raw}.{table_name}"

        logger.info("Loading to BigQuery", table=target, rows=len(df), run_id=run_id)

        try:
            from google.cloud import bigquery  # type: ignore

            # Snapshot tables — always full replace
            if table_name in ("products",):
                job_config = bigquery.LoadJobConfig(
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                    autodetect=True,
                )
                job = self.client.load_table_from_dataframe(df, target, job_config=job_config)
                job.result()
                logger.info("Table loaded (truncate)", table=target, rows=len(df))
                return len(df)

            # Transactional tables — MERGE via temp table
            temp_table = f"{target}_temp_{run_id.replace('-', '_')}"

            # 1. Write to temp table
            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                autodetect=True,
            )
            job = self.client.load_table_from_dataframe(df, temp_table, job_config=job_config)
            job.result()

            # 2. MERGE into target
            merge_key = _get_merge_key(table_name)
            all_cols = ", ".join(df.columns)
            update_cols = ", ".join(
                f"T.{c} = S.{c}" for c in df.columns if c != merge_key
            )
            insert_cols = all_cols
            insert_vals = ", ".join(f"S.{c}" for c in df.columns)

            merge_sql = f"""
                MERGE `{target}` T
                USING `{temp_table}` S
                ON T.{merge_key} = S.{merge_key}
                WHEN MATCHED THEN
                    UPDATE SET {update_cols}
                WHEN NOT MATCHED THEN
                    INSERT ({insert_cols})
                    VALUES ({insert_vals})
            """
            self.client.query(merge_sql).result()

            # 3. Drop temp table
            self.client.delete_table(temp_table, not_found_ok=True)

            logger.info("Table loaded (merge)", table=target, rows=len(df))
            return len(df)

        except Exception as exc:
            logger.error("BigQuery load failed", table=target, error=str(exc), exc_info=True)
            raise


def _get_merge_key(table_name: str) -> str:
    keys = {
        "orders":      "order_id",
        "order_items": "item_id",
        "customers":   "customer_id",
        "products":    "product_id",
    }
    return keys.get(table_name, "id")
