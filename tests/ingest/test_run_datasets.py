import gzip
import json
from datetime import UTC, datetime

import pytest

from tests.ingest.test_datasets import make_zip
from xbrl_reconcile.config import Company
from xbrl_reconcile.ingest.datasets import quarter_key
from xbrl_reconcile.ingest.http import HttpError
from xbrl_reconcile.ingest.run_datasets import (
    QUARTERS_STATE_KEY,
    expected_ciks,
    quarters_to_fetch,
    run_datasets_ingestion,
)
from xbrl_reconcile.ingest.storage import LocalStorage

NOW = datetime(2026, 10, 15, 6, 0, 0, tzinfo=UTC)


def company(cik, ticker, start_year=2009, end_year=None, enabled=True):
    return Company(
        cik=cik,
        ticker=ticker,
        name=ticker,
        start_year=start_year,
        end_year=end_year,
        enabled=enabled,
        report_types=("10-K",),
    )


class FakeQuarterClient:
    """Serves a zip per quarter; a value that is an Exception is raised."""

    def __init__(self, by_quarter):
        self.by_quarter = dict(by_quarter)
        self.requested = []

    def get(self, url):
        quarter = url.rsplit("/", 1)[-1].removesuffix(".zip")
        self.requested.append(quarter)
        value = self.by_quarter.get(quarter, HttpError(f"GET {url} failed with status 404"))
        if isinstance(value, Exception):
            raise value
        return value


def test_a_companys_own_start_year_beats_the_global_default():
    companies = [company(1, "OLD", start_year=2009), company(2, "NEW", start_year=2025)]
    assert expected_ciks("2012q1", companies) == {1}
    assert expected_ciks("2025q1", companies) == {1, 2}


def test_the_year_after_end_year_is_included_but_not_the_next():
    """A final fiscal year is reported in a filing submitted the following year."""
    companies = [company(1, "GONE", end_year=2022)]
    assert expected_ciks("2022q4", companies) == {1}
    assert expected_ciks("2023q2", companies) == {1}
    assert expected_ciks("2024q1", companies) == set()


def test_a_disabled_company_is_not_expected_anywhere():
    assert expected_ciks("2020q1", [company(1, "OFF", enabled=False)]) == set()


def test_a_quarter_already_covering_the_expectation_is_not_refetched():
    companies = [company(1, "AAA", start_year=2025)]
    state = {"2025q1": {"ciks": [1]}}
    assert "2025q1" not in quarters_to_fetch(companies, state, NOW)


def test_adding_a_company_refetches_only_the_quarters_its_range_covers():
    companies = [company(1, "AAA", start_year=2009), company(2, "NEW", start_year=2026)]
    state = {q: {"ciks": [1]} for q in ("2025q4", "2026q1", "2026q2")}

    todo = quarters_to_fetch(companies, state, NOW)

    assert "2025q4" not in todo, "the new company's range does not reach 2025"
    assert "2026q1" in todo and "2026q2" in todo


def test_quarters_are_ordered_oldest_first_and_stop_at_the_current_one():
    companies = [company(1, "AAA", start_year=2025)]
    todo = quarters_to_fetch(companies, {}, NOW)
    assert todo[0] == "2025q1"
    assert todo[-1] == "2026q4", "the quarter containing today is the last candidate"
    assert todo == sorted(todo)


def test_a_quarter_not_published_yet_is_skipped_without_failing(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({"2026q1": make_zip()})
    companies = [company(1327811, "WDAY", start_year=2026)]

    result = run_datasets_ingestion(companies, client, storage, NOW)

    assert result.landed == ["2026q1"]
    assert "2026q2" in result.not_published
    assert result.failed == {}


def test_another_http_error_is_a_failure_and_does_not_stop_the_rest(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient(
        {
            "2026q1": HttpError("GET failed with status 500"),
            "2026q2": make_zip(),
            "2026q3": make_zip(),
            "2026q4": make_zip(),
        }
    )
    companies = [company(1327811, "WDAY", start_year=2026)]

    result = run_datasets_ingestion(companies, client, storage, NOW)

    assert "500" in result.failed["2026q1"]
    assert result.landed == ["2026q2", "2026q3", "2026q4"]


def test_the_batch_limit_stops_after_n_oldest_first(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({q: make_zip() for q in ("2026q1", "2026q2", "2026q3", "2026q4")})
    companies = [company(1327811, "WDAY", start_year=2026)]

    result = run_datasets_ingestion(companies, client, storage, NOW, max_quarters=2)

    assert result.landed == ["2026q1", "2026q2"]
    assert client.requested == ["2026q1", "2026q2"]


def test_a_landed_quarter_writes_five_files_and_updates_state(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({"2026q1": make_zip()})
    companies = [
        company(1327811, "WDAY", start_year=2026),
        company(896878, "INTU", start_year=2026),
    ]

    run_datasets_ingestion(companies, client, storage, NOW, max_quarters=1)

    for name in ("sub", "num", "pre", "tag"):
        assert storage.read(quarter_key("2026q1", name)) is not None
    recorded = json.loads(storage.read(quarter_key("2026q1", "_filtered_for")))
    assert recorded["filings"] == 2

    state = json.loads(storage.read(QUARTERS_STATE_KEY))
    assert state["2026q1"]["ciks"] == [896878, 1327811]
    assert state["2026q1"]["facts"] == 4
    assert state["2026q1"]["landed_at"] == "2026-10-15T060000Z"


def test_a_second_run_fetches_nothing(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({q: make_zip() for q in ("2026q1", "2026q2", "2026q3", "2026q4")})
    companies = [company(1327811, "WDAY", start_year=2026)]
    run_datasets_ingestion(companies, client, storage, NOW)
    requested_first = len(client.requested)

    result = run_datasets_ingestion(companies, client, storage, NOW)

    assert result.landed == []
    assert len(client.requested) == requested_first, "no further downloads"


def test_stored_rows_are_the_filtered_bytes(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({"2026q1": make_zip()})
    run_datasets_ingestion(
        [company(1327811, "WDAY", start_year=2026)], client, storage, NOW, max_quarters=1
    )

    num = gzip.decompress(storage.read(quarter_key("2026q1", "num"))).decode()
    assert "ProductOrService=SubscriptionServices;" in num
    assert "0000320193" not in num, "another filer's rows are not stored"


def test_missing_start_year_range_means_no_work(tmp_path):
    """Every company disabled: nothing to fetch, and no error."""
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({})
    result = run_datasets_ingestion([company(1, "OFF", enabled=False)], client, storage, NOW)
    assert result.landed == [] and result.failed == {}
    assert client.requested == []


def test_an_unparseable_archive_is_reported_as_a_failure(tmp_path):
    storage = LocalStorage(tmp_path)
    client = FakeQuarterClient({"2026q1": b"not a zip"})
    companies = [company(1, "AAA", start_year=2026)]

    result = run_datasets_ingestion(companies, client, storage, NOW, max_quarters=1)

    assert "2026q1" in result.failed
    with pytest.raises(AssertionError):
        assert storage.read(quarter_key("2026q1", "num")) is not None
