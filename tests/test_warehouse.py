import pytest

from xbrl_reconcile.ingest.storage import LocalStorage
from xbrl_reconcile.warehouse import WAREHOUSE_KEY, fetch_warehouse, publish_warehouse


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


def test_fetch_writes_the_stored_database(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")
    storage.write(WAREHOUSE_KEY, b"duckdb-bytes")
    target = tmp_path / "transform" / "xbrl.duckdb"

    found = fetch_warehouse(target, storage)

    assert found is True
    assert target.read_bytes() == b"duckdb-bytes"


def test_fetch_is_not_an_error_when_nothing_is_stored(tmp_path):
    """The first ever run has no database to reuse, which is normal."""
    target = tmp_path / "transform" / "xbrl.duckdb"

    found = fetch_warehouse(target, LocalStorage(tmp_path / "bucket"))

    assert found is False
    assert not target.exists()


def test_fetch_replaces_a_stale_local_database(tmp_path):
    storage = LocalStorage(tmp_path / "bucket")
    storage.write(WAREHOUSE_KEY, b"from-bucket")
    target = tmp_path / "xbrl.duckdb"
    target.write_bytes(b"stale-local")

    fetch_warehouse(target, storage)

    assert target.read_bytes() == b"from-bucket"
