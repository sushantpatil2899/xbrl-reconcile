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
    config_snapshot_key,
    make_s3_client,
    snapshot_key,
)
from xbrl_reconcile.mappings import MappingConfig, load_mappings, validate_against_companies

log = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"


@dataclass
class RunResult:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def run_ingestion(
    companies: list[Company],
    api,
    storage,
    now: datetime,
    mappings: MappingConfig | None = None,
) -> RunResult:
    run_ts = now.astimezone(UTC).strftime(TIMESTAMP_FORMAT)

    # Validate before any request: a broken mapping config should fail at second
    # zero, not after 28 downloads, and must never reach the bucket.
    if mappings is not None:
        for warning in validate_against_companies(mappings, companies):
            log.warning("%s", warning)

    seen_by_cik = _read_state(storage)
    result = RunResult()

    for company in companies:
        if not company.enabled:
            continue
        try:
            submissions = api.submissions(company.cik10)
            accession = latest_report_accession(submissions, company.report_types)
            seen = seen_by_cik.get(company.cik10)
            if seen is not None and seen["accession"] == accession:
                result.skipped.append(company.ticker)
                continue

            companyfacts = api.companyfacts(company.cik10)
            for dataset, body in (("submissions", submissions), ("companyfacts", companyfacts)):
                storage.write(
                    snapshot_key(dataset, company.cik10, run_ts), gzip.compress(body, mtime=0)
                )
            seen_by_cik[company.cik10] = {
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

    # last_run is a heartbeat written on every run, including runs that download
    # nothing, so staleness can be detected without mistaking a quiet week for a
    # broken pipeline.
    state = {"last_run": run_ts, "companies": seen_by_cik}
    storage.write(STATE_KEY, json.dumps(state, indent=2, sort_keys=True).encode())
    _write_config_snapshot(companies, storage, run_ts)
    if mappings is not None:
        _write_mapping_snapshots(mappings, storage, run_ts)
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
    mappings = load_mappings(Path(os.environ.get("MAPPINGS_PATH", "config/tag_mappings.yml")))
    contact = _require(os.environ, "SEC_CONTACT_EMAIL")
    client = PoliteClient(user_agent=f"xbrl-reconcile {contact}")
    storage = build_storage(os.environ)

    result = run_ingestion(companies, SecApi(client), storage, datetime.now(UTC), mappings=mappings)

    log.info(
        "done: %d downloaded, %d skipped, %d failed",
        len(result.downloaded),
        len(result.skipped),
        len(result.failed),
    )
    for ticker, error in result.failed.items():
        log.error("failed %s: %s", ticker, error)
    return 1 if result.failed else 0


def _write_config_snapshot(companies: list[Company], storage, run_ts: str) -> None:
    """Store the company list as data, so the bucket records which list produced this run."""
    rows = [
        {
            "cik": c.cik,
            "cik10": c.cik10,
            "ticker": c.ticker,
            "name": c.name,
            "description": c.description,
            # `group` is a reserved word in SQL, so the column is group_name.
            "group_name": c.group,
            "start_year": c.start_year,
            "end_year": c.end_year,
            "enabled": c.enabled,
        }
        for c in companies
    ]
    storage.write(config_snapshot_key("companies", run_ts), json.dumps(rows, indent=2).encode())


def _write_mapping_snapshots(mappings: MappingConfig, storage, run_ts: str) -> None:
    """Store the mapping rules as data. Every published value traces back to these."""
    for name, rows in (
        ("tag_mappings", mappings.concept_rows()),
        ("tag_mapping_overrides", mappings.override_rows()),
        ("tag_components", mappings.component_rows()),
        ("tag_summable_axes", mappings.summable_axis_rows()),
    ):
        storage.write(config_snapshot_key(name, run_ts), json.dumps(rows, indent=2).encode())


def _read_state(storage) -> dict:
    """Return the per company state, accepting the shape used before last_run existed."""
    data = storage.read(STATE_KEY)
    if not data:
        return {}
    state = json.loads(data)
    if "companies" in state:
        return state["companies"]
    return state


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ValueError(f"missing environment variable {name}")
    return value
