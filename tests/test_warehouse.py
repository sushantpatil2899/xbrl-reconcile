import pytest

from xbrl_reconcile.ingest.storage import LocalStorage
from xbrl_reconcile.warehouse import WAREHOUSE_KEY, publish_warehouse


def test_uploads_database_file(tmp_path):
    db = tmp_path / "xbrl.duckdb"
    db.write_bytes(b"duckdb-bytes")
    storage = LocalStorage(tmp_path / "bucket")

    size = publish_warehouse(db, storage)

    assert size == len(b"duckdb-bytes")
    assert storage.read(WAREHOUSE_KEY) == b"duckdb-bytes"


def test_publishing_replaces_the_previous_database(tmp_path):
    db = tmp_path / "xbrl.duckdb"
    storage = LocalStorage(tmp_path / "bucket")
    db.write_bytes(b"first")
    publish_warehouse(db, storage)

    db.write_bytes(b"second")
    publish_warehouse(db, storage)

    assert storage.read(WAREHOUSE_KEY) == b"second"


def test_missing_database_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="xbrl.duckdb"):
        publish_warehouse(tmp_path / "xbrl.duckdb", LocalStorage(tmp_path))
