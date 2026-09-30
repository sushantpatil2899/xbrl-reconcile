"""Land the calculation linkbase of every annual report we do not already have.

Which filings to fetch comes from the landed companyfacts snapshots rather than
from the submissions ones, and the reason is a measurement. SEC puts only the most
recent thousand filings in a submissions response, and Salesforce files about 172
documents a year, so that block reaches back roughly six years and would offer 6 of
its 18 annual reports. companyfacts carries the accession and form on every fact and
only for filings that reported XBRL, which is 74 filings for Salesforce and reaches
2010. The mappings most in need of evidence are historical, so the source has to
reach that far.

A filing is immutable once accepted, so anything already fetched is never fetched
again, and a filing with no calculation linkbase is recorded as having none rather
than retried on every run.
"""

import gzip
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from xbrl_reconcile.config import Company, load_companies
from xbrl_reconcile.ingest.http import PoliteClient
from xbrl_reconcile.ingest.linkbase import (
    LINKBASE_PREFIX,
    calculation_filename,
    index_url,
    linkbase_key,
    linkbase_url,
    parse_calculation_arcs,
)
from xbrl_reconcile.ingest.run import build_storage
from xbrl_reconcile.ingest.storage import STATE_KEY, Storage, snapshot_key

log = logging.getLogger(__name__)

LINKBASE_STATE_KEY = f"{LINKBASE_PREFIX}/_state/filings.json"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"
DEFAULT_MAX_FILINGS = 300

# The annual forms among the report types config allows. Config decides which forms
# count as a report at all; this narrows that to the ones covering a whole year,
# because a 10-Q's linkbase describes the same tags as its year's 10-K.
ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A")


@dataclass
class LinkbaseRunResult:
    landed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    no_linkbase: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def annual_report_accessions(companyfacts: bytes, forms: tuple[str, ...]) -> dict[str, str]:
    """Accession to form, for every annual report that reported a fact."""
    facts = json.loads(companyfacts).get("facts", {})
    found: dict[str, str] = {}
    for taxonomy in facts.values():
        for concept in taxonomy.values():
            for entries in concept.get("units", {}).values():
                for entry in entries:
                    if entry.get("form") in forms and entry.get("accn"):
                        found[entry["accn"]] = entry["form"]
    return found


def annual_forms_for(company: Company) -> tuple[str, ...]:
    """The annual forms this company's config allows, so config still governs."""
    return tuple(form for form in ANNUAL_FORMS if form in company.report_types)


def filings_to_fetch(
    companies: list[Company], storage: Storage, state: dict
) -> list[tuple[Company, str, str]]:
    """Company, accession and form for annual reports not yet landed, oldest first."""
    ingest_state = _read_ingest_state(storage)
    todo: list[tuple[Company, str, str]] = []
    for company in companies:
        if not company.enabled:
            continue
        seen = ingest_state.get(company.cik10)
        if not seen or not seen.get("snapshot"):
            log.warning(
                "%s has no companyfacts snapshot recorded; run the ingest job", company.ticker
            )
            continue
        body = storage.read(snapshot_key("companyfacts", company.cik10, seen["snapshot"]))
        if body is None:
            log.warning("%s companyfacts snapshot %s is missing", company.ticker, seen["snapshot"])
            continue
        accessions = annual_report_accessions(gzip.decompress(body), annual_forms_for(company))
        for accession, form in sorted(accessions.items()):
            if accession not in state:
                todo.append((company, accession, form))
    return todo


def run_linkbase_ingestion(
    companies: list[Company],
    client,
    storage: Storage,
    now: datetime,
    max_filings: int = DEFAULT_MAX_FILINGS,
) -> LinkbaseRunResult:
    state = _read_state(storage)
    result = LinkbaseRunResult()
    todo = filings_to_fetch(companies, storage, state)
    if len(todo) > max_filings:
        result.skipped = [accession for _, accession, _ in todo[max_filings:]]
        todo = todo[:max_filings]

    run_ts = now.astimezone(UTC).strftime(TIMESTAMP_FORMAT)
    for company, accession, form in todo:
        try:
            listing = client.get(index_url(company.cik, accession))
            filename = calculation_filename(listing)
            if filename is None:
                # Early filings often have no calculation linkbase. Recording it stops
                # the run asking again every month for something that will never exist.
                state[accession] = {
                    "ticker": company.ticker,
                    "form": form,
                    "linkbase": None,
                    "arcs": 0,
                    "fetched_at": run_ts,
                }
                result.no_linkbase.append(accession)
                log.info("%s %s has no calculation linkbase", company.ticker, accession)
                continue

            xml = client.get(linkbase_url(company.cik, accession, filename))
            arcs = parse_calculation_arcs(xml)
            storage.write(
                linkbase_key(company.cik10, accession, "cal.xml.gz"), gzip.compress(xml, mtime=0)
            )
            storage.write(
                linkbase_key(company.cik10, accession, "arcs.json"),
                json.dumps(arcs, indent=2).encode(),
            )
            state[accession] = {
                "ticker": company.ticker,
                "form": form,
                "linkbase": filename,
                "arcs": len(arcs),
                "fetched_at": run_ts,
            }
            result.landed.append(accession)
            log.info("%s %s: %d arcs from %s", company.ticker, accession, len(arcs), filename)
        except Exception as err:
            log.error("%s %s failed: %s", company.ticker, accession, err)
            result.failed[accession] = str(err)

    storage.write(LINKBASE_STATE_KEY, json.dumps(state, indent=2, sort_keys=True).encode())
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    companies = load_companies(Path(os.environ.get("CONFIG_PATH", "config/companies.yml")))
    contact = os.environ.get("SEC_CONTACT_EMAIL")
    if not contact:
        raise ValueError("missing environment variable SEC_CONTACT_EMAIL")
    max_filings = int(os.environ.get("MAX_FILINGS", DEFAULT_MAX_FILINGS))

    result = run_linkbase_ingestion(
        companies,
        PoliteClient(user_agent=f"xbrl-reconcile {contact}"),
        build_storage(os.environ),
        datetime.now(UTC),
        max_filings=max_filings,
    )

    log.info(
        "done: %d landed, %d without a linkbase, %d failed, %d left for a later run",
        len(result.landed),
        len(result.no_linkbase),
        len(result.failed),
        len(result.skipped),
    )
    for accession, error in result.failed.items():
        log.error("failed %s: %s", accession, error)
    return 1 if result.failed else 0


def _read_state(storage: Storage) -> dict:
    data = storage.read(LINKBASE_STATE_KEY)
    return json.loads(data) if data else {}


def _read_ingest_state(storage: Storage) -> dict:
    """Per company state from the ingest job, which records the newest snapshot."""
    data = storage.read(STATE_KEY)
    if not data:
        return {}
    state = json.loads(data)
    return state.get("companies", state)
