import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from xbrl_reconcile.ingest.storage import LocalStorage
from xbrl_reconcile.publish_marts import INDEX_KEY, mart_key, publish_marts

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
