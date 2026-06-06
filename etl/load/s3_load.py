"""
S3 loader — saves DataFrames as parquet (partitioned by date).

In development: saves to local /tmp/ecommerce-pipeline/data/ instead of S3.
Set S3_BUCKET env var to switch to real S3.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd

from src.config_loader import get_config
from src.logger import get_logger

logger = get_logger(__name__)


class S3Loader:
    """Saves DataFrames as parquet to S3 or local filesystem."""

    LOCAL_BASE = Path("/tmp/ecommerce-pipeline/data")

    def __init__(self) -> None:
        self._cfg = get_config().s3
        self._use_local = not self._cfg.access_key_id
        if self._use_local:
            self.LOCAL_BASE.mkdir(parents=True, exist_ok=True)
            logger.info("S3Loader using local filesystem (no AWS credentials found)")

    def save(
        self,
        df: pd.DataFrame,
        table: str,
        run_date: date,
        stage: str = "raw",
        run_id: str = "",
    ) -> str:
        """
        Save DataFrame as parquet.

        Args:
            df:       DataFrame to save.
            table:    Table name (orders, customers, etc.).
            run_date: Partition date.
            stage:    raw | processed.
            run_id:   Pipeline run ID for the filename.

        Returns:
            Path/URI where the file was saved.
        """
        if df.empty:
            logger.warning("Skipping save — empty DataFrame", table=table)
            return ""

        filename = f"{run_id or 'data'}.parquet"
        key = f"{stage}/{table}/date={run_date.isoformat()}/{filename}"

        if self._use_local:
            return self._save_local(df, key)
        return self._save_s3(df, key)

    def load(self, table: str, run_date: date, stage: str = "raw") -> pd.DataFrame:
        """Load a saved parquet file back into a DataFrame."""
        prefix = f"{stage}/{table}/date={run_date.isoformat()}/"

        if self._use_local:
            return self._load_local(prefix)
        return self._load_s3(prefix)

    # ── Local filesystem ──────────────────────────────────────────────────────

    def _save_local(self, df: pd.DataFrame, key: str) -> str:
        path = self.LOCAL_BASE / key
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
        logger.info("Saved to local", path=str(path), rows=len(df))
        return str(path)

    def _load_local(self, prefix: str) -> pd.DataFrame:
        dir_path = self.LOCAL_BASE / prefix
        if not dir_path.exists():
            return pd.DataFrame()
        files = list(dir_path.glob("*.parquet"))
        if not files:
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    # ── S3 ────────────────────────────────────────────────────────────────────

    def _save_s3(self, df: pd.DataFrame, key: str) -> str:
        try:
            import boto3  # type: ignore
            buf = io.BytesIO()
            df.to_parquet(buf, index=False, engine="pyarrow", compression="snappy")
            buf.seek(0)
            s3 = boto3.client(
                "s3",
                region_name=self._cfg.region,
                aws_access_key_id=self._cfg.access_key_id,
                aws_secret_access_key=self._cfg.secret_access_key.get_secret_value(),
            )
            s3.put_object(Bucket=self._cfg.bucket, Key=key, Body=buf.getvalue())
            uri = f"s3://{self._cfg.bucket}/{key}"
            logger.info("Saved to S3", uri=uri, rows=len(df))
            return uri
        except ImportError:
            raise RuntimeError("boto3 not installed. Run: pip install boto3")

    def _load_s3(self, prefix: str) -> pd.DataFrame:
        try:
            import boto3  # type: ignore
            s3 = boto3.client("s3", region_name=self._cfg.region)
            response = s3.list_objects_v2(Bucket=self._cfg.bucket, Prefix=prefix)
            files = [obj["Key"] for obj in response.get("Contents", [])]
            if not files:
                return pd.DataFrame()
            dfs = []
            for key in files:
                obj = s3.get_object(Bucket=self._cfg.bucket, Key=key)
                dfs.append(pd.read_parquet(io.BytesIO(obj["Body"].read())))
            return pd.concat(dfs, ignore_index=True)
        except ImportError:
            raise RuntimeError("boto3 not installed. Run: pip install boto3")
