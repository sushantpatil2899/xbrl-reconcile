from tests.ingest.fakes import submissions_json
from xbrl_reconcile.ingest.sec import SecApi, latest_report_accession

REPORTS = ("10-K", "10-Q")


class RecordingClient:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return b"{}"


def test_urls_use_zero_padded_cik():
    client = RecordingClient()
    api = SecApi(client)
    api.submissions("0001108524")
    api.companyfacts("0001108524")
    assert client.urls == [
        "https://data.sec.gov/submissions/CIK0001108524.json",
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0001108524.json",
    ]


def test_latest_report_ignores_non_financial_forms():
    doc = submissions_json(
        [
            ("4", "acc-insider", "2026-09-10"),
            ("10-Q", "acc-q2", "2026-09-03"),
            ("8-K", "acc-8k", "2026-08-01"),
        ]
    )
    assert latest_report_accession(doc, REPORTS) == "acc-q2"


def test_latest_report_picks_newest_filing_date_regardless_of_order():
    doc = submissions_json([("10-K", "acc-old", "2026-03-01"), ("10-Q", "acc-new", "2026-06-01")])
    assert latest_report_accession(doc, REPORTS) == "acc-new"


def test_latest_report_is_none_without_matching_forms():
    doc = submissions_json([("4", "acc-insider", "2026-09-10")])
    assert latest_report_accession(doc, REPORTS) is None
