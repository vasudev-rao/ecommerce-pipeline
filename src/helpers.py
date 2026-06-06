"""Shared utility helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Generator, Iterable
from datetime import date, datetime, timedelta, timezone
from typing import TypeVar

T = TypeVar("T")

DATE_FORMAT = "%Y-%m-%d"


def generate_run_id(pipeline: str, run_date: date) -> str:
    """Deterministic run ID — same inputs always produce same ID."""
    key = f"{pipeline}:{run_date.isoformat()}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"{pipeline}-{run_date.isoformat()}-{digest}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def yesterday() -> date:
    return (datetime.now(timezone.utc) - timedelta(days=1)).date()


def date_range(start: date, end: date) -> Generator[date, None, None]:
    """Yield each date from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def parse_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), DATE_FORMAT).date()


def chunk_iterable(iterable: Iterable[T], chunk_size: int) -> Generator[list[T], None, None]:
    """Split an iterable into fixed-size chunks."""
    chunk: list[T] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def send_slack_alert(message: str, webhook_url: str) -> None:
    """Send a Slack alert. Silent failure — never crash the pipeline."""
    if not webhook_url:
        return
    try:
        import json, urllib.request
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"text": message}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
