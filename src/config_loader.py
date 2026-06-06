"""
Config loader — reads base.yaml and overrides with environment variables.

Usage:
    from src.config_loader import get_config
    cfg = get_config()
    print(cfg.database.host)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, SecretStr


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    name: str = "ecommerce_db"
    user: str = "ecommerce_user"
    password: SecretStr = SecretStr("changeme")
    pool_size: int = 5

    @property
    def url(self) -> str:
        pwd = self.password.get_secret_value()
        return f"postgresql://{self.user}:{pwd}@{self.host}:{self.port}/{self.name}"


class BigQueryConfig(BaseModel):
    project_id: str = ""
    dataset_raw: str = "ecommerce_raw"
    dataset_staging: str = "ecommerce_staging"
    dataset_mart: str = "ecommerce_mart"
    location: str = "US"


class S3Config(BaseModel):
    bucket: str = "ecommerce-pipeline-data"
    region: str = "us-east-1"
    raw_prefix: str = "raw"
    processed_prefix: str = "processed"
    access_key_id: str = ""
    secret_access_key: SecretStr = SecretStr("")


class PipelineConfig(BaseModel):
    batch_chunk_size: int = 5000
    schedule_cron: str = "0 2 * * *"
    lookback_days: int = 1
    data_retention_days: int = 90


class ObservabilityConfig(BaseModel):
    log_level: str = "INFO"
    log_format: str = "json"
    slack_webhook_url: str = ""


class AppConfig(BaseModel):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    bigquery: BigQueryConfig = Field(default_factory=BigQueryConfig)
    s3: S3Config = Field(default_factory=S3Config)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _inject_env_vars(config: dict[str, Any]) -> dict[str, Any]:
    env_map = {
        "DB_HOST":             ("database", "host"),
        "DB_PORT":             ("database", "port"),
        "DB_NAME":             ("database", "name"),
        "DB_USER":             ("database", "user"),
        "DB_PASSWORD":         ("database", "password"),
        "BQ_PROJECT_ID":       ("bigquery", "project_id"),
        "BQ_DATASET_RAW":      ("bigquery", "dataset_raw"),
        "AWS_REGION":          ("s3", "region"),
        "S3_BUCKET":           ("s3", "bucket"),
        "AWS_ACCESS_KEY_ID":   ("s3", "access_key_id"),
        "AWS_SECRET_ACCESS_KEY":("s3","secret_access_key"),
        "LOG_LEVEL":           ("observability", "log_level"),
        "SLACK_WEBHOOK_URL":   ("observability", "slack_webhook_url"),
    }
    for env_var, key_path in env_map.items():
        value = os.getenv(env_var)
        if value is not None:
            node = config
            for k in key_path[:-1]:
                node = node.setdefault(k, {})
            node[key_path[-1]] = value
    return config


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    base_dir = Path(__file__).parents[1] / "config"
    raw = _load_yaml(base_dir / "base.yaml")
    raw = _inject_env_vars(raw)
    return AppConfig(**raw)


def reload_config() -> AppConfig:
    get_config.cache_clear()
    return get_config()
