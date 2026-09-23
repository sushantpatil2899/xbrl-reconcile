"""Publish the built DuckDB database to object storage.

The transform job runs on a machine that is wiped afterwards, so the database
has to be uploaded or the run produces nothing. It is written to a fixed key
and overwrites the previous copy: the database is rebuildable from the raw
layer, so its history is not worth keeping.
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_PATH))
    size = publish_warehouse(path, build_storage(os.environ))
    log.info("published %s (%.1f MB) to %s", path, size / 1_000_000, WAREHOUSE_KEY)
    return 0
