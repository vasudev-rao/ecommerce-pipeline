"""Unit tests for src/helpers.py"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.helpers import (
    chunk_iterable,
    date_range,
    generate_run_id,
    parse_date,
    yesterday,
)


class TestGenerateRunId:
    def test_contains_pipeline_and_date(self):
        run_id = generate_run_id("batch", date(2024, 1, 15))
        assert "batch" in run_id
        assert "2024-01-15" in run_id

    def test_deterministic(self):
        id1 = generate_run_id("batch", date(2024, 1, 15))
        id2 = generate_run_id("batch", date(2024, 1, 15))
        assert id1 == id2

    def test_different_dates_different_ids(self):
        id1 = generate_run_id("batch", date(2024, 1, 15))
        id2 = generate_run_id("batch", date(2024, 1, 16))
        assert id1 != id2


class TestDateRange:
    def test_single_day(self):
        result = list(date_range(date(2024, 1, 1), date(2024, 1, 1)))
        assert result == [date(2024, 1, 1)]

    def test_inclusive_range(self):
        result = list(date_range(date(2024, 1, 1), date(2024, 1, 5)))
        assert len(result) == 5
        assert result[0] == date(2024, 1, 1)
        assert result[-1] == date(2024, 1, 5)

    def test_empty_when_start_after_end(self):
        result = list(date_range(date(2024, 1, 10), date(2024, 1, 5)))
        assert result == []


class TestParseDate:
    def test_parses_string(self):
        assert parse_date("2024-01-15") == date(2024, 1, 15)

    def test_returns_date_unchanged(self):
        d = date(2024, 6, 1)
        assert parse_date(d) == d

    def test_extracts_from_datetime(self):
        dt = datetime(2024, 6, 1, 12, 0)
        assert parse_date(dt) == date(2024, 6, 1)

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestChunkIterable:
    def test_even_split(self):
        chunks = list(chunk_iterable(range(9), 3))
        assert len(chunks) == 3
        assert all(len(c) == 3 for c in chunks)

    def test_uneven_split(self):
        chunks = list(chunk_iterable(range(10), 3))
        assert len(chunks) == 4
        assert len(chunks[-1]) == 1

    def test_empty_input(self):
        assert list(chunk_iterable([], 5)) == []

    def test_larger_than_input(self):
        chunks = list(chunk_iterable([1, 2, 3], 100))
        assert chunks == [[1, 2, 3]]
