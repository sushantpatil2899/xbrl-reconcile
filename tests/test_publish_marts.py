import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from xbrl_reconcile.ingest.storage import LocalStorage
from xbrl_reconcile.publish_marts import (
    INDEX_KEY,
    INDEX_NAME,
    MartVerificationError,
    fetch_marts,
    mart_key,
    publish_marts,
)

NOW = datetime(2026, 9, 27, 6, 12, 4, tzinfo=UTC)


def warehouse(path: Path) -> Path:
    """A database shaped like the real one: two marts and the layers beneath them."""
    connection = duckdb.connect(str(path))
    connection.execute("create table mart_financials as select 1 as cik, 100.0 as value")
    connection.execute(
        "create table mart_balance_sheet as "
        "select * from (values (1, 10.0), (2, 20.0)) as t(cik, total_assets)"
    )
    connection.execute("create table stg_sec_facts as select 1 as cik")
    connection.execute("create table int_facts as select 1 as cik")
    connection.close()
    return path


def test_only_the_marts_are_published(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")

    publish_marts(warehouse(tmp_path / "xbrl.duckdb"), storage, NOW)

    assert storage.read(mart_key("mart_financials")) is not None
    assert storage.read(mart_key("mart_balance_sheet")) is not None
    assert storage.read(mart_key("stg_sec_facts")) is None, "staging is not a mart"
    assert storage.read(mart_key("int_facts")) is None


def test_the_index_records_row_counts_and_when_it_ran(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")

    publish_marts(warehouse(tmp_path / "xbrl.duckdb"), storage, NOW)

    index = json.loads(storage.read(INDEX_KEY))
    assert index["published_at"] == "2026-09-27T06:12:04Z"
    assert [(mart["name"], mart["rows"]) for mart in index["marts"]] == [
        ("mart_balance_sheet", 2),
        ("mart_financials", 1),
    ]
    assert all(mart["bytes"] > 0 for mart in index["marts"])


def test_a_published_file_is_readable_on_its_own(tmp_path):
    """The point of the export: a reader needs the file, not the warehouse."""
    storage = LocalStorage(tmp_path / "bucket")
    publish_marts(warehouse(tmp_path / "xbrl.duckdb"), storage, NOW)

    landed = tmp_path / "bucket" / mart_key("mart_balance_sheet")
    rows = (
        duckdb.connect()
        .execute(f"select cik, total_assets from '{landed}' order by cik")
        .fetchall()
    )

    assert rows == [(1, 10.0), (2, 20.0)]


def test_a_database_with_no_marts_still_writes_an_index(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")
    path = tmp_path / "empty.duckdb"
    duckdb.connect(str(path)).close()

    published = publish_marts(path, storage, NOW)

    assert published == []
    assert json.loads(storage.read(INDEX_KEY))["marts"] == []


def test_a_missing_database_is_an_error_rather_than_an_empty_publish(tmp_path):
    with pytest.raises(FileNotFoundError):
        publish_marts(tmp_path / "absent.duckdb", LocalStorage(tmp_path), NOW)


def published(tmp_path) -> LocalStorage:
    """A bucket holding a real publish, which is what every fetch test starts from."""
    storage = LocalStorage(tmp_path / "bucket")
    publish_marts(warehouse(tmp_path / "xbrl.duckdb"), storage, NOW)
    return storage


def rewrite_index(storage, name: str, **changes) -> None:
    """Change what the index claims about one mart, leaving the file itself alone."""
    index = json.loads(storage.read(INDEX_KEY))
    for mart in index["marts"]:
        if mart["name"] == name:
            mart.update(changes)
    storage.write(INDEX_KEY, json.dumps(index).encode())


def test_the_fetch_lands_every_mart_and_the_index_beside_them(tmp_path):
    destination = tmp_path / "marts"

    index = fetch_marts(destination, published(tmp_path))

    assert index["published_at"] == "2026-09-27T06:12:04Z"
    assert sorted(path.name for path in destination.iterdir()) == [
        INDEX_NAME,
        "mart_balance_sheet.parquet",
        "mart_financials.parquet",
    ]


def test_a_fetched_file_is_readable_on_its_own(tmp_path):
    """The whole point: the serving layer opens these without the database."""
    destination = tmp_path / "marts"
    fetch_marts(destination, published(tmp_path))

    landed = destination / "mart_balance_sheet.parquet"
    rows = (
        duckdb.connect()
        .execute(f"select cik, total_assets from '{landed}' order by cik")
        .fetchall()
    )

    assert rows == [(1, 10.0), (2, 20.0)]


def test_a_truncated_download_is_rejected_and_nothing_is_written(tmp_path):
    """The reason the fetch verifies: a short file reads fine and answers short."""
    storage = published(tmp_path)
    whole = storage.read(mart_key("mart_financials"))
    storage.write(mart_key("mart_financials"), whole[: len(whole) // 2])
    destination = tmp_path / "marts"

    with pytest.raises(MartVerificationError, match="mart_financials is "):
        fetch_marts(destination, storage)

    assert not destination.exists(), "a failed fetch must not leave a partial set"


def test_a_row_count_that_disagrees_with_the_index_is_rejected(tmp_path):
    """Separate from the length check: a file can be the right size and wrong."""
    storage = published(tmp_path)
    rewrite_index(storage, "mart_financials", rows=99)

    with pytest.raises(MartVerificationError, match="has 1 rows, the index says 99"):
        fetch_marts(tmp_path / "marts", storage)


def test_a_file_that_is_not_parquet_is_rejected_rather_than_raised_from(tmp_path):
    storage = published(tmp_path)
    storage.write(mart_key("mart_financials"), b"not parquet")
    rewrite_index(storage, "mart_financials", bytes=len(b"not parquet"))

    with pytest.raises(MartVerificationError, match="not readable as Parquet"):
        fetch_marts(tmp_path / "marts", storage)


def test_every_failure_is_reported_not_just_the_first(tmp_path):
    storage = published(tmp_path)
    rewrite_index(storage, "mart_financials", rows=99)
    rewrite_index(storage, "mart_balance_sheet", rows=98)

    with pytest.raises(MartVerificationError) as raised:
        fetch_marts(tmp_path / "marts", storage)

    assert "2 of 2 marts" in str(raised.value)
    assert "mart_financials" in str(raised.value)
    assert "mart_balance_sheet" in str(raised.value)


def test_a_mart_listed_but_absent_is_rejected(tmp_path):
    storage = published(tmp_path)
    (tmp_path / "bucket" / mart_key("mart_financials")).unlink()

    with pytest.raises(MartVerificationError, match="not in storage"):
        fetch_marts(tmp_path / "marts", storage)


def test_nothing_published_yet_is_reported_rather_than_failing(tmp_path):
    assert fetch_marts(tmp_path / "marts", LocalStorage(tmp_path / "empty")) is None
