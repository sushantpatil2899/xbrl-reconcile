"""Land new SEC snapshots for every enabled company in the config."""

import gzip
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from xbrl_reconcile.config import Company, load_companies
from xbrl_reconcile.ingest.http import PoliteClient
from xbrl_reconcile.ingest.sec import SecApi, latest_report_accession
from xbrl_reconcile.ingest.storage import (
    STATE_KEY,
    LocalStorage,
    S3Storage,
    make_s3_client,
    snapshot_key,
)

log = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"


@dataclass
class RunResult:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def run_ingestion(companies: list[Company], api, storage, now: datetime) -> RunResult:
    run_ts = now.astimezone(UTC).strftime(TIMESTAMP_FORMAT)
    state = _read_state(storage)
    result = RunResult()

    for company in companies:
        if not company.enabled:
            continue
        try:
            submissions = api.submissions(company.cik10)
            accession = latest_report_accession(submissions, company.report_types)
            seen = state.get(company.cik10)
            if seen is not None and seen["accession"] == accession:
                result.skipped.append(company.ticker)
                continue

            companyfacts = api.companyfacts(company.cik10)
            for dataset, body in (("submissions", submissions), ("companyfacts", companyfacts)):
                storage.write(
                    snapshot_key(dataset, company.cik10, run_ts), gzip.compress(body, mtime=0)
                )
            state[company.cik10] = {
                "ticker": company.ticker,
                "accession": accession,
                "snapshot": run_ts,
            }
            result.downloaded.append(company.ticker)
            log.info("%s downloaded (latest report %s)", company.ticker, accession)
        except Exception as err:
            # One company failing must not stop the others; it is reported at the end.
            log.error("%s failed: %s", company.ticker, err)
            result.failed[company.ticker] = str(err)

    storage.write(STATE_KEY, json.dumps(state, indent=2, sort_keys=True).encode())
    return result


def build_storage(env: Mapping[str, str]):
    backend = env.get("STORAGE_BACKEND", "local")
    if backend == "local":
        return LocalStorage(Path(env.get("LOCAL_DATA_DIR", "data")))
    if backend == "b2":
        bucket = _require(env, "B2_BUCKET")
        client = make_s3_client(
            _require(env, "B2_ENDPOINT"),
            _require(env, "B2_INGEST_KEY_ID"),
            _require(env, "B2_INGEST_KEY"),
        )
        return S3Storage(bucket, client)
    raise ValueError(f"unknown STORAGE_BACKEND: {backend}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    companies = load_companies(Path(os.environ.get("CONFIG_PATH", "config/companies.yml")))
    contact = _require(os.environ, "SEC_CONTACT_EMAIL")
    client = PoliteClient(user_agent=f"xbrl-reconcile {contact}")
    storage = build_storage(os.environ)

    result = run_ingestion(companies, SecApi(client), storage, datetime.now(UTC))

    log.info(
        "done: %d downloaded, %d skipped, %d failed",
        len(result.downloaded),
        len(result.skipped),
        len(result.failed),
    )
    for ticker, error in result.failed.items():
        log.error("failed %s: %s", ticker, error)
    return 1 if result.failed else 0


def _read_state(storage) -> dict:
    data = storage.read(STATE_KEY)
    return json.loads(data) if data else {}


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ValueError(f"missing environment variable {name}")
    return value
