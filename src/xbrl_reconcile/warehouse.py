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
    size = publish_warehouse(path, build_storage(os.environ))
    log.info("published %s (%.1f MB) to %s", path, size / 1_000_000, WAREHOUSE_KEY)
    return 0


def fetch_main() -> int:
    """Fetch the previous database so the run can build on it instead of rebuilding."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    if fetch_warehouse(path, build_storage(os.environ)):
        log.info(
            "fetched %s (%.1f MB) from %s", path, path.stat().st_size / 1_000_000, WAREHOUSE_KEY
        )
    else:
        log.info("no database at %s yet; models will build from scratch", WAREHOUSE_KEY)
    return 0
