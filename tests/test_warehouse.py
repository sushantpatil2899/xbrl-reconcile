import gzip
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from xbrl_reconcile.ingest.storage import LocalStorage, S3Storage
from xbrl_reconcile.warehouse import (
    WAREHOUSE_KEY,
    fetch_main,
    fetch_warehouse,
    publish_warehouse,
)


def test_uploads_database_gzipped(tmp_path):
    """The only read a quiet transform run makes, so it is worth compressing: the
    real database is 88 MB on disk and 16.7 MB stored."""
    db = tmp_path / "xbrl.duckdb"
    db.write_bytes(b"duckdb-bytes" * 500)
    storage = LocalStorage(tmp_path / "bucket")

    on_disk, stored = publish_warehouse(db, storage)

    assert on_disk == len(b"duckdb-bytes" * 500)
    assert stored < on_disk
    assert gzip.decompress(storage.read(WAREHOUSE_KEY)) == b"duckdb-bytes" * 500


def test_publishing_replaces_the_previous_database(tmp_path):
    db = tmp_path / "xbrl.duckdb"
    storage = LocalStorage(tmp_path / "bucket")
    db.write_bytes(b"first")
    publish_warehouse(db, storage)

    db.write_bytes(b"second")
    publish_warehouse(db, storage)

    assert gzip.decompress(storage.read(WAREHOUSE_KEY)) == b"second"


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


def test_storage_can_say_where_it_reads_and_writes():
    assert LocalStorage(Path("data")).location == "local folder data"
    assert S3Storage("a-bucket", client=None).location == "bucket a-bucket"


def test_a_missing_database_says_where_it_looked(tmp_path, caplog):
    """An absent database, the wrong backend and the wrong bucket all look the same.

    Only the location tells them apart, and in CI a silent miss means every model
    rebuilds from scratch with a slow job as the only symptom.
    """
    environment = {
        "STORAGE_BACKEND": "local",
        "LOCAL_DATA_DIR": str(tmp_path / "empty"),
        "WAREHOUSE_PATH": str(tmp_path / "xbrl.duckdb"),
    }

    with caplog.at_level(logging.WARNING), patch.dict(os.environ, environment, clear=False):
        fetch_main()

    assert f"local folder {tmp_path / 'empty'}" in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


def test_fetching_expands_what_publishing_compressed(tmp_path):
    db = tmp_path / "xbrl.duckdb"
    db.write_bytes(b"duckdb-bytes" * 500)
    storage = LocalStorage(tmp_path / "bucket")
    publish_warehouse(db, storage)
    restored = tmp_path / "restored.duckdb"

    assert fetch_warehouse(restored, storage) is True
    assert restored.read_bytes() == b"duckdb-bytes" * 500


def test_an_uncompressed_copy_is_still_readable(tmp_path):
    """What earlier runs wrote, and what a database restored by hand would look
    like. The format is detected from the bytes, so the switch needed no migration."""
    storage = LocalStorage(tmp_path / "bucket")
    storage.write(WAREHOUSE_KEY, b"plain-duckdb-bytes")
    restored = tmp_path / "restored.duckdb"

    assert fetch_warehouse(restored, storage) is True
    assert restored.read_bytes() == b"plain-duckdb-bytes"
