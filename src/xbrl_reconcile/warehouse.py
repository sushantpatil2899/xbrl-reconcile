"""Move the DuckDB database between the transform machine and object storage.

The transform job runs on a machine that is wiped afterwards, so the database
is fetched before the run and published after it. Without the fetch the table
never exists at the start of a run, every model rebuilds from scratch, and the
incremental logic has nothing to build on.

The database is written to a fixed key and overwrites the previous copy: it is
rebuildable from the raw layer, so its history is not worth keeping.
"""

import logging
import os
from pathlib import Path

from xbrl_reconcile.ingest.run import build_storage

log = logging.getLogger(__name__)

WAREHOUSE_KEY = "warehouse/xbrl.duckdb"
DEFAULT_PATH = "transform/xbrl.duckdb"


def publish_warehouse(path: Path, storage) -> int:
    """Upload the database file and return how many bytes were written."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no database at {path}")
    data = path.read_bytes()
    storage.write(WAREHOUSE_KEY, data)
    return len(data)


def fetch_warehouse(path: Path, storage) -> bool:
    """Write the stored database to path. Returns False when there is none yet."""
    path = Path(path)
    data = storage.read(WAREHOUSE_KEY)
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    storage = build_storage(os.environ)
    size = publish_warehouse(path, storage)
    log.info(
        "published %s (%.1f MB) to %s in %s",
        path,
        size / 1_000_000,
        WAREHOUSE_KEY,
        storage.location,
    )
    return 0


def fetch_main() -> int:
    """Fetch the previous database so the run can build on it instead of rebuilding."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    storage = build_storage(os.environ)
    if fetch_warehouse(path, storage):
        log.info(
            "fetched %s (%.1f MB) from %s in %s",
            path,
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
