"""SEC EDGAR endpoints and detection of new financial reports."""

import json

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"


class SecApi:
    def __init__(self, client):
        self._client = client

    def submissions(self, cik10: str) -> bytes:
        return self._client.get(SUBMISSIONS_URL.format(cik10=cik10))

    def companyfacts(self, cik10: str) -> bytes:
        return self._client.get(COMPANYFACTS_URL.format(cik10=cik10))


def latest_report_accession(submissions: bytes, report_types: tuple[str, ...]) -> str | None:
    """Accession number of the most recently filed report whose form is in report_types."""
    recent = json.loads(submissions)["filings"]["recent"]
    matches = [
        (filing_date, accession)
        for form, accession, filing_date in zip(
            recent["form"], recent["accessionNumber"], recent["filingDate"], strict=True
        )
        if form in report_types
    ]
    if not matches:
        return None
    return max(matches)[1]
