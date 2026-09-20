from tests.ingest.fakes import FakeSecApi, submissions_json
from xbrl_reconcile.config import Company
from xbrl_reconcile.ingest.check_ciks import check_company
from xbrl_reconcile.ingest.http import HttpError


def company(ticker="CRM"):
    return Company(
        cik=1108524,
        ticker=ticker,
        name="Salesforce",
        start_year=2009,
        end_year=None,
        enabled=True,
        report_types=("10-K",),
    )


def api_with(doc):
    return FakeSecApi(submissions={"0001108524": doc})


def test_ok_when_ticker_matches():
    api = api_with(submissions_json([], name="Salesforce, Inc.", tickers=["CRM"]))
    assert check_company(company(), api) == ("OK", "Salesforce, Inc.")


def test_no_ticker_for_delisted_company():
    api = api_with(submissions_json([], name="SPLUNK INC", tickers=[]))
    assert check_company(company("SPLK"), api) == ("NO TICKER", "SPLUNK INC")


def test_mismatch_when_ticker_differs():
    api = api_with(submissions_json([], name="Other Co", tickers=["OTH"]))
    assert check_company(company(), api) == ("MISMATCH", "Other Co")


def test_error_when_fetch_fails():
    api = api_with(HttpError("GET failed with status 404"))
    status, detail = check_company(company(), api)
    assert status == "ERROR"
    assert "404" in detail
