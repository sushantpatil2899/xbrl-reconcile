import gzip
import json
from datetime import UTC, datetime

from tests.ingest.test_linkbase import LINKBASE
from xbrl_reconcile.config import Company
from xbrl_reconcile.ingest.http import HttpError
from xbrl_reconcile.ingest.linkbase import linkbase_key
from xbrl_reconcile.ingest.run_linkbase import (
    LINKBASE_STATE_KEY,
    annual_forms_for,
    annual_report_accessions,
    run_linkbase_ingestion,
)
from xbrl_reconcile.ingest.storage import STATE_KEY, LocalStorage, snapshot_key

NOW = datetime(2026, 9, 29, 6, 0, 0, tzinfo=UTC)
SNAPSHOT = "2026-09-28T060000Z"


def company(cik=1108524, ticker="CRM", report_types=("10-K", "10-Q", "20-F"), enabled=True):
    return Company(
        cik=cik,
        ticker=ticker,
        name=ticker,
        start_year=2009,
        end_year=None,
        enabled=enabled,
        report_types=report_types,
    )


def companyfacts(entries):
    """A companyfacts response shaped like SEC's, carrying accession and form per fact."""
    return gzip.compress(
        json.dumps({"facts": {"us-gaap": {"Revenues": {"units": {"USD": entries}}}}}).encode()
    )


def landed(storage, entries, cik10="0001108524"):
    storage.write(
        STATE_KEY,
        json.dumps({"companies": {cik10: {"ticker": "CRM", "snapshot": SNAPSHOT}}}).encode(),
    )
    storage.write(snapshot_key("companyfacts", cik10, SNAPSHOT), companyfacts(entries))


class FakeEdgar:
    """Serves an index listing and a linkbase per filing; an Exception is raised."""

    def __init__(self, by_url):
        self.by_url = dict(by_url)
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        value = self.by_url.get(url)
        if value is None:
            raise HttpError(f"GET {url} failed with status 404")
        if isinstance(value, Exception):
            raise value
        return value


def listing(name="crm-20180131_cal.xml"):
    items = [{"name": "crm-20180131.xml"}]
    if name:
        items.append({"name": name})
    return json.dumps({"directory": {"item": items}}).encode()


def edgar_for(accession="0001108524-18-000011", cal=LINKBASE, name="crm-20180131_cal.xml"):
    base = f"https://www.sec.gov/Archives/edgar/data/1108524/{accession.replace('-', '')}"
    served = {f"{base}/index.json": listing(name)}
    if name:
        served[f"{base}/{name}"] = cal
    return FakeEdgar(served)


def test_only_annual_reports_are_fetched():
    entries = [
        {"accn": "0001108524-18-000011", "form": "10-K"},
        {"accn": "0001108524-18-000087", "form": "10-Q"},
        {"accn": "0001108524-18-000099", "form": "DEF 14A"},
    ]
    accessions = annual_report_accessions(
        json.dumps({"facts": {"us-gaap": {"R": {"units": {"USD": entries}}}}}).encode(),
        ("10-K", "10-K/A", "20-F", "20-F/A"),
    )

    assert accessions == {"0001108524-18-000011": "10-K"}


def test_config_still_decides_which_forms_count():
    """A company configured without 20-F never has one fetched."""
    assert annual_forms_for(company(report_types=("10-K", "10-Q"))) == ("10-K",)
    assert "20-F" in annual_forms_for(company(report_types=("10-K", "20-F")))


def test_a_landed_filing_stores_the_xml_and_the_flattened_arcs(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])

    result = run_linkbase_ingestion([company()], edgar_for(), storage, NOW)

    assert result.landed == ["0001108524-18-000011"]
    stored = storage.read(linkbase_key("0001108524", "0001108524-18-000011", "cal.xml.gz"))
    assert gzip.decompress(stored) == LINKBASE, "the raw file is kept exactly as served"
    arcs = json.loads(storage.read(linkbase_key("0001108524", "0001108524-18-000011", "arcs.json")))
    assert len(arcs) == 3
    assert arcs[0]["parent"] == "us-gaap_GrossProfit"


def test_a_filing_with_no_linkbase_is_recorded_rather_than_retried(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])

    result = run_linkbase_ingestion([company()], edgar_for(name=None), storage, NOW)

    assert result.no_linkbase == ["0001108524-18-000011"]
    assert result.failed == {}
    state = json.loads(storage.read(LINKBASE_STATE_KEY))
    assert state["0001108524-18-000011"]["linkbase"] is None


def test_a_second_run_fetches_nothing(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])
    client = edgar_for()
    run_linkbase_ingestion([company()], client, storage, NOW)
    first = len(client.requested)

    result = run_linkbase_ingestion([company()], client, storage, NOW)

    assert result.landed == []
    assert len(client.requested) == first, "a filing is immutable, so it is never refetched"


def test_the_batch_limit_leaves_the_rest_for_a_later_run(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(
        storage,
        [
            {"accn": "0001108524-18-000011", "form": "10-K"},
            {"accn": "0001108524-19-000009", "form": "10-K"},
        ],
    )

    result = run_linkbase_ingestion([company()], edgar_for(), storage, NOW, max_filings=1)

    assert result.landed == ["0001108524-18-000011"]
    assert result.skipped == ["0001108524-19-000009"]


def test_one_failure_does_not_stop_the_others(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(
        storage,
        [
            {"accn": "0001108524-18-000011", "form": "10-K"},
            {"accn": "0001108524-19-000009", "form": "10-K"},
        ],
    )
    client = edgar_for()
    broken = "https://www.sec.gov/Archives/edgar/data/1108524/000110852419000009/index.json"
    client.by_url[broken] = HttpError("GET failed with status 500")

    result = run_linkbase_ingestion([company()], client, storage, NOW)

    assert result.landed == ["0001108524-18-000011"]
    assert "500" in result.failed["0001108524-19-000009"]


def test_a_company_with_no_snapshot_is_reported_rather_than_crashing(tmp_path):
    storage = LocalStorage(tmp_path)

    result = run_linkbase_ingestion([company()], FakeEdgar({}), storage, NOW)

    assert result.landed == [] and result.failed == {}


def test_a_disabled_company_is_not_fetched(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])
    client = edgar_for()

    run_linkbase_ingestion([company(enabled=False)], client, storage, NOW)

    assert client.requested == []


def test_a_filing_edgar_does_not_serve_is_recorded_rather_than_retried(tmp_path):
    """companyfacts references filings EDGAR has no directory for. Retrying a 404
    every month would leave the job permanently red for something that cannot heal."""
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-21-000014", "form": "10-K"}])
    client = FakeEdgar({})  # every URL 404s

    result = run_linkbase_ingestion([company()], client, storage, NOW)

    assert result.unavailable == ["0001108524-21-000014"]
    assert result.failed == {}, "a permanent absence is not a failure to report"
    state = json.loads(storage.read(LINKBASE_STATE_KEY))
    assert state["0001108524-21-000014"]["unavailable"] is True

    again = run_linkbase_ingestion([company()], client, storage, NOW)
    assert again.unavailable == [], "and it is not asked for a second time"


def test_another_http_error_is_still_a_failure(tmp_path):
    """Only a 404 is permanent. A 500 should be retried next month."""
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])
    client = edgar_for()
    index = "https://www.sec.gov/Archives/edgar/data/1108524/000110852418000011/index.json"
    client.by_url[index] = HttpError("GET failed with status 500")

    result = run_linkbase_ingestion([company()], client, storage, NOW)

    assert "500" in result.failed["0001108524-18-000011"]
    assert result.unavailable == []


def test_a_format_bump_reparses_from_stored_xml_without_a_request(tmp_path):
    """The raw file is kept as published precisely so this costs no requests."""
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])
    client = edgar_for()
    run_linkbase_ingestion([company()], client, storage, NOW)
    requests_after_fetch = len(client.requested)

    # An older run stored arcs in the first format.
    state = json.loads(storage.read(LINKBASE_STATE_KEY))
    state["0001108524-18-000011"]["arcs_format"] = 1
    storage.write(LINKBASE_STATE_KEY, json.dumps(state).encode())

    result = run_linkbase_ingestion([company()], client, storage, NOW)

    assert result.reparsed == ["0001108524-18-000011"]
    assert len(client.requested) == requests_after_fetch, "no request is made to re-parse"
    arcs = json.loads(storage.read(linkbase_key("0001108524", "0001108524-18-000011", "arcs.json")))
    assert all("child_schema" in arc for arc in arcs)


def test_a_filing_already_at_the_current_format_is_left_alone(tmp_path):
    storage = LocalStorage(tmp_path)
    landed(storage, [{"accn": "0001108524-18-000011", "form": "10-K"}])
    run_linkbase_ingestion([company()], edgar_for(), storage, NOW)

    result = run_linkbase_ingestion([company()], edgar_for(), storage, NOW)

    assert result.reparsed == []
