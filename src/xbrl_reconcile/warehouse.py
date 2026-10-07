"""Move the DuckDB database between the transform machine and object storage.

The transform job runs on a machine that is wiped afterwards, so the database
is fetched before the run and published after it. Without the fetch the table
never exists at the start of a run, every model rebuilds from scratch, and the
incremental logic has nothing to build on.

The database is written to a fixed key and overwrites the previous copy: it is
rebuildable from the raw layer, so its history is not worth keeping.

It is stored gzipped, which matters because this is the only read a quiet
transform run makes. Once the staging models became incremental the raw layer
costs nothing on a day with no new filings, leaving this fetch as the whole
bandwidth cost, and a DuckDB file is mostly compressible: 88 MB becomes 16.7 MB.
At the default level that costs 0.8 seconds to compress and 0.1 to expand. Level
1 saves four tenths of a second for 1.4 MB more, and level 9 spends 2.2 seconds
to save 0.1 MB, so the default is the right end of the curve.

Whether the stored copy is compressed is decided by reading its first two bytes
rather than by its name. The key does not change, so the switch needed no
migration, and a rollback would still read what the new code wrote.
"""

import gzip
import logging
import os
from pathlib import Path

from xbrl_reconcile.ingest.run import build_storage

log = logging.getLogger(__name__)

WAREHOUSE_KEY = "warehouse/xbrl.duckdb"
DEFAULT_PATH = "transform/xbrl.duckdb"


# gzip's magic number. Read from the stored bytes so the format is detected rather
# than assumed, which is what let compression arrive without a migration.
GZIP_MAGIC = b"\x1f\x8b"


def publish_warehouse(path: Path, storage) -> tuple[int, int]:
    """Upload the database gzipped. Returns the size on disk and the size stored."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no database at {path}")
    data = path.read_bytes()
    compressed = gzip.compress(data, mtime=0)
    storage.write(WAREHOUSE_KEY, compressed)
    return len(data), len(compressed)


def fetch_warehouse(path: Path, storage) -> int | None:
    """Write the stored database to path and return how many bytes were downloaded.

    Returns None when there is nothing stored yet. The downloaded size is returned
    rather than the size on disk, because once the copy is compressed those differ by
    five times and the transferred figure is the one that costs anything.

    An uncompressed copy is accepted too, because that is what earlier runs wrote
    and what a database restored by hand would look like.
    """
    path = Path(path)
    data = storage.read(WAREHOUSE_KEY)
    if data is None:
        return None
    downloaded = len(data)
    if data[:2] == GZIP_MAGIC:
        data = gzip.decompress(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return downloaded


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    storage = build_storage(os.environ)
    on_disk, stored = publish_warehouse(path, storage)
    log.info(
        "published %s (%.1f MB, %.1f MB gzipped) to %s in %s",
        path,
        on_disk / 1_000_000,
        stored / 1_000_000,
        WAREHOUSE_KEY,
        storage.location,
    )
    return 0


def fetch_main() -> int:
    """Fetch the previous database so the run can build on it instead of rebuilding."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    storage = build_storage(os.environ)
    downloaded = fetch_warehouse(path, storage)
    if downloaded is not None:
        log.info(
            "fetched %s (%.1f MB downloaded, %.1f MB on disk) from %s in %s",
            path,
            downloaded / 1_000_000,
            path.stat().st_size / 1_000_000,
            WAREHOUSE_KEY,
            storage.location,
        )
    else:
        # Naming the location matters more than it looks. An absent database, the
        # wrong backend and the wrong bucket all produce this line, and only the
        # location tells them apart. Reported as a warning because in CI a silent
        # miss means every model rebuilds from scratch and the only symptom is a
        # slow job.
        log.warning(
            "no database at %s in %s; models will build from scratch",
            WAREHOUSE_KEY,
            storage.location,
        )
    return 0
