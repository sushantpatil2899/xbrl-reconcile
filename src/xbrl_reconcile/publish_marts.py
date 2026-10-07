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

The fetch is the counterpart, and it verifies rather than trusts. The index records
each file's size and row count, so a download can be checked against what the publish
promised. That check is the reason the fetch exists as code instead of a copy command:
a truncated transfer that is served anyway returns short answers to every later
question, and nothing downstream would notice.
"""

import json
import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from xbrl_reconcile.ingest.run import build_storage

log = logging.getLogger(__name__)

PARQUET_PREFIX = "warehouse/parquet"
INDEX_NAME = "_index.json"
INDEX_KEY = f"{PARQUET_PREFIX}/{INDEX_NAME}"
MART_PREFIX = "mart_"
DEFAULT_PATH = "transform/xbrl.duckdb"
DEFAULT_MARTS_PATH = "warehouse/parquet"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class MartVerificationError(Exception):
    """A downloaded mart did not match what the index promised."""


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


def fetch_marts(destination: Path, storage) -> dict | None:
    """Download every mart the index lists, verify it, and write it to destination.

    Returns the index that was honoured, or None when nothing has been published yet.

    Nothing reaches destination until every file has passed, so a bad download leaves
    whatever was there alone instead of half replacing it with a set that reads
    successfully and answers short. The index is written alongside the files, which
    means the serving layer has the row counts and the publish time without needing
    credentials for the bucket.
    """
    destination = Path(destination)
    raw = storage.read(INDEX_KEY)
    if raw is None:
        return None
    index = json.loads(raw)
    marts = index.get("marts", [])

    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary)
        # Every mart is checked before any is accepted. Stopping at the first failure
        # would report one bad file when the publish may have broken for six.
        problems = [
            problem for mart in marts if (problem := _verify(mart, staged, storage)) is not None
        ]
        if problems:
            raise MartVerificationError(
                f"{len(problems)} of {len(marts)} marts did not match the index: "
                + "; ".join(problems)
            )
        destination.mkdir(parents=True, exist_ok=True)
        for mart in marts:
            name = _filename(mart["name"])
            # move rather than replace: the staging directory is wherever the system
            # puts temporary files, which is not always the same filesystem.
            shutil.move(str(staged / name), str(destination / name))
        (destination / INDEX_NAME).write_bytes(raw)

    return index


def _verify(mart: dict, staged: Path, storage) -> str | None:
    """Download one mart and check it against the index. Returns what was wrong, if so."""
    name = mart["name"]
    data = storage.read(mart_key(name))
    if data is None:
        return f"{name} is in the index but not in storage"
    # The length check is nearly free and catches a truncated transfer before anything
    # tries to parse it.
    if len(data) != mart["bytes"]:
        return f"{name} is {len(data)} bytes, the index says {mart['bytes']}"

    local = staged / _filename(name)
    local.write_bytes(data)
    # Counting the rows is the check that matters: it proves the bytes are a readable
    # Parquet file holding what was published, not merely a blob of the right size.
    try:
        rows = _row_count(local)
    except duckdb.Error as error:
        return f"{name} is not readable as Parquet ({error})"
    if rows != mart["rows"]:
        return f"{name} has {rows} rows, the index says {mart['rows']}"
    return None


def _row_count(path: Path) -> int:
    connection = duckdb.connect()
    try:
        return connection.execute("select count(*) from read_parquet(?)", [str(path)]).fetchone()[0]
    finally:
        connection.close()


def _filename(name: str) -> str:
    """One definition of what a mart file is called, shared with the publish."""
    return Path(mart_key(name)).name


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    storage = build_storage(os.environ)
    published = publish_marts(path, storage, datetime.now(UTC))
    log.info(
        "published %d marts (%.0f KB) to %s in %s",
        len(published),
        sum(mart["bytes"] for mart in published) / 1024,
        PARQUET_PREFIX,
        storage.location,
    )
    return 0


def fetch_main() -> int:
    """Fetch the published marts, so the serving layer never needs the database."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    destination = Path(os.environ.get("MARTS_PATH", DEFAULT_MARTS_PATH))
    storage = build_storage(os.environ)
    index = fetch_marts(destination, storage)
    if index is None:
        # Fatal rather than a warning, unlike the warehouse fetch. A missing warehouse
        # means a slow rebuild; missing marts mean there is nothing to serve at all.
        log.error("nothing published at %s in %s", INDEX_KEY, storage.location)
        return 1

    marts = index.get("marts", [])
    # Bytes downloaded and bytes on disk are the same figure here, unlike the
    # warehouse: Parquet carries its zstd compression inside the file, so there is
    # nothing to unwrap and no second number to report the wrong one of.
    log.info(
        "fetched %d marts (%.0f KB) published %s to %s from %s",
        len(marts),
        sum(mart["bytes"] for mart in marts) / 1024,
        index.get("published_at", "at an unrecorded time"),
        destination,
        storage.location,
    )
    return 0
