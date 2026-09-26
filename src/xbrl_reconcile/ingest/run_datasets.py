"""Land the quarters of SEC's Financial Statement Data Sets that we still need.

Which quarters a company needs comes from the company config: a quarter is needed
when the company is enabled and the quarter's year falls between its start_year
and its end_year plus one. The plus one is because a final fiscal year is reported
in a filing submitted the following calendar year. Quarters before start_year are
never needed, because a period can only appear in a filing submitted at or after
it.

Each landed quarter records the CIKs it was filtered for. A quarter is fetched
when the CIKs it should cover are not already a subset of what it recorded, so
adding a company re-fetches only the quarters its own range covers, and removing
one re-fetches nothing.

SEC publishes a quarter about six weeks after it ends, so a missing quarter is
normal rather than a failure.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from xbrl_reconcile.config import Company, load_companies
from xbrl_reconcile.ingest.datasets import (
    FSDS_PREFIX,
    dataset_url,
    filter_quarter,
    quarter_key,
    quarters_between,
)
from xbrl_reconcile.ingest.http import PoliteClient
from xbrl_reconcile.ingest.run import build_storage
from xbrl_reconcile.ingest.storage import Storage

log = logging.getLogger(__name__)

QUARTERS_STATE_KEY = f"{FSDS_PREFIX}/_state/quarters.json"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"
DEFAULT_MAX_QUARTERS = 8
NOT_PUBLISHED = "404"


@dataclass
class DatasetRunResult:
    landed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    not_published: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def expected_ciks(quarter: str, companies: list[Company]) -> set[int]:
    """The companies whose history this quarter should contain."""
    year = int(quarter[:4])
    return {
        c.cik
        for c in companies
        if c.enabled and year >= c.start_year and year <= (c.end_year + 1 if c.end_year else 9999)
    }


def quarters_to_fetch(companies: list[Company], state: dict, now: datetime) -> list[str]:
    """Quarters whose recorded companies do not yet cover what they should, oldest first."""
    enabled = [c for c in companies if c.enabled]
    if not enabled:
        return []
    first_year = min(c.start_year for c in enabled)
    candidates = quarters_between(first_year, now.year)

    todo = []
    for quarter in candidates:
        wanted = expected_ciks(quarter, companies)
        if not wanted:
            continue
        recorded = set(state.get(quarter, {}).get("ciks", []))
        if not wanted.issubset(recorded):
            todo.append(quarter)
    return todo


def run_datasets_ingestion(
    companies: list[Company],
    client,
    storage: Storage,
    now: datetime,
    max_quarters: int = DEFAULT_MAX_QUARTERS,
) -> DatasetRunResult:
    state = _read_state(storage)
    result = DatasetRunResult()
    todo = quarters_to_fetch(companies, state, now)
    if len(todo) > max_quarters:
        result.skipped = todo[max_quarters:]
        todo = todo[:max_quarters]

    for quarter in todo:
        wanted = expected_ciks(quarter, companies)
        try:
            archive = client.get(dataset_url(quarter))
            files = filter_quarter(archive, wanted)
        except Exception as err:
            message = str(err)
            # SEC publishes a quarter about six weeks after it ends, so a quarter
            # that does not exist yet is expected rather than broken.
            if NOT_PUBLISHED in message:
                log.info("%s is not published yet", quarter)
                result.not_published.append(quarter)
            else:
                log.error("%s failed: %s", quarter, message)
                result.failed[quarter] = message
            continue

        for name, data in files.items():
            storage.write(quarter_key(quarter, name), data)
        recorded = json.loads(files["_filtered_for"])
        state[quarter] = {
            "ciks": recorded["ciks"],
            "filings": recorded["filings"],
            "facts": recorded["facts"],
            "landed_at": now.astimezone(UTC).strftime(TIMESTAMP_FORMAT),
        }
        result.landed.append(quarter)
        log.info("%s landed: %d filings, %d facts", quarter, recorded["filings"], recorded["facts"])

    storage.write(QUARTERS_STATE_KEY, json.dumps(state, indent=2, sort_keys=True).encode())
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    companies = load_companies(Path(os.environ.get("CONFIG_PATH", "config/companies.yml")))
    contact = os.environ.get("SEC_CONTACT_EMAIL")
    if not contact:
        raise ValueError("missing environment variable SEC_CONTACT_EMAIL")
    max_quarters = int(os.environ.get("MAX_QUARTERS", DEFAULT_MAX_QUARTERS))

    result = run_datasets_ingestion(
        companies,
        PoliteClient(user_agent=f"xbrl-reconcile {contact}"),
        build_storage(os.environ),
        datetime.now(UTC),
        max_quarters=max_quarters,
    )

    log.info(
        "done: %d landed, %d not published yet, %d failed, %d left for a later run",
        len(result.landed),
        len(result.not_published),
        len(result.failed),
        len(result.skipped),
    )
    for quarter, error in result.failed.items():
        log.error("failed %s: %s", quarter, error)
    return 1 if result.failed else 0


def _read_state(storage: Storage) -> dict:
    data = storage.read(QUARTERS_STATE_KEY)
    return json.loads(data) if data else {}
