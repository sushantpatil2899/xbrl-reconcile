"""Export the mart tables as Parquet, so a reader fetches kilobytes not a database.

The published database is 56 MB, most of it staging tables and raw facts that
nobody querying a financial statement needs. The same marts as Parquet are about
1 MB in total, and each file stands alone: reading the income statement costs a
hundred kilobytes rather than the whole warehouse. Parquet stores each column
separately and typed, so a query touching three columns reads only those three,
and repeated values like a tag name are stored once.

DuckDB writes the files locally and the same Storage object the rest of the
pipeline uses uploads them. DuckDB can write straight to the bucket, and the dbt
profile already holds credentials for reading it, but going through Storage keeps
one way of talking to the bucket and lets the whole export be tested with a
temporary database and no credentials at all.

Which tables to export comes from the database, not from a list here: anything in
the main schema named mart_ is a mart. Adding a mart publishes it.
"""

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from xbrl_reconcile.ingest.run import build_storage

log = logging.getLogger(__name__)

PARQUET_PREFIX = "warehouse/parquet"
INDEX_KEY = f"{PARQUET_PREFIX}/_index.json"
MART_PREFIX = "mart_"
DEFAULT_PATH = "transform/xbrl.duckdb"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def mart_key(name: str) -> str:
    return f"{PARQUET_PREFIX}/{name}.parquet"


def mart_tables(connection) -> list[str]:
    """Every mart in the database, in name order."""
    rows = connection.execute(
        "select table_name from duckdb_tables() "
        "where schema_name = 'main' and starts_with(table_name, ?) "
        "order by table_name",
        [MART_PREFIX],
    ).fetchall()
    return [row[0] for row in rows]


def publish_marts(path: Path, storage, now: datetime, workdir: Path | None = None) -> list[dict]:
    """Write every mart to the bucket as Parquet and return what was published."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no database at {path}")

    with tempfile.TemporaryDirectory() as temporary:
        out = Path(workdir) if workdir else Path(temporary)
        out.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(path), read_only=True)
        try:
            published = [
                _export(connection, name, out, storage) for name in mart_tables(connection)
            ]
        finally:
            connection.close()

    if not published:
        log.warning("no tables named %s in %s", f"{MART_PREFIX}*", path)

    # Written last, so an index never promises a file that is not there. It lets a
    # reader see what exists and how fresh it is without downloading anything.
    index = {
        "published_at": now.astimezone(UTC).strftime(TIMESTAMP_FORMAT),
        "marts": published,
    }
    storage.write(INDEX_KEY, json.dumps(index, indent=2).encode())
    return published


def _export(connection, name: str, out: Path, storage) -> dict:
    """Write one mart to Parquet, upload it, and describe what was written."""
    local = out / f"{name}.parquet"
    # zstd is built into DuckDB's Parquet writer and smaller than the default.
    connection.execute(
        f"copy (select * from main.\"{name}\") to '{local}' (format parquet, compression zstd)"
    )
    data = local.read_bytes()
    storage.write(mart_key(name), data)
    rows = connection.execute(f'select count(*) from main."{name}"').fetchone()[0]
    log.info("%s: %d rows, %.0f KB", name, rows, len(data) / 1024)
    return {"name": name, "rows": rows, "bytes": len(data)}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    published = publish_marts(path, build_storage(os.environ), datetime.now(UTC))
    log.info(
        "published %d marts (%.0f KB) to %s",
        len(published),
        sum(mart["bytes"] for mart in published) / 1024,
        PARQUET_PREFIX,
    )
    return 0
