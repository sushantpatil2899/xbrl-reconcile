"""What uvicorn points at: uvicorn xbrl_reconcile.api.asgi:app

Separate from app.py on purpose. Opening the marts is file I/O, and doing it while a
module is being imported would make every test that imports the app module depend on
a directory of Parquet existing. Here it is correct to fail fast: a serving process
with no data to serve should refuse to start rather than answer nothing.

Rate limits come from the environment so a host can loosen or tighten them without a
rebuild. The defaults allow 60 requests a minute per address.
"""

import logging
import os

from xbrl_reconcile.api.app import create_app, store_from_environment

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = create_app(
    store_from_environment(),
    rate=float(os.environ.get("RATE_PER_SECOND", "1")),
    burst=int(os.environ.get("RATE_BURST", "60")),
)
