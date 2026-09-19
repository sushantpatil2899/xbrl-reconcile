"""Test doubles for network, time and SEC access."""

import json
import urllib.error


class FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Returns or raises scripted outcomes in order and records each request."""

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClock:
    """A clock that only moves when sleep is called."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.test", code, "error", None, None)


def submissions_json(filings, name="Test Co", tickers=None) -> bytes:
    """Build a minimal submissions document. Each filing is (form, accession, filing_date)."""
    return json.dumps(
        {
            "name": name,
            "tickers": ["TEST"] if tickers is None else tickers,
            "filings": {
                "recent": {
                    "form": [f[0] for f in filings],
                    "accessionNumber": [f[1] for f in filings],
                    "filingDate": [f[2] for f in filings],
                }
            },
        }
    ).encode()


class FakeSecApi:
    """Serves scripted responses per CIK; a value that is an Exception is raised."""

    def __init__(self, submissions=None, companyfacts=None):
        self.submissions_by_cik = dict(submissions or {})
        self.companyfacts_by_cik = dict(companyfacts or {})
        self.calls = []

    def submissions(self, cik10: str) -> bytes:
        self.calls.append(("submissions", cik10))
        return self._serve(self.submissions_by_cik[cik10])

    def companyfacts(self, cik10: str) -> bytes:
        self.calls.append(("companyfacts", cik10))
        return self._serve(self.companyfacts_by_cik[cik10])

    @staticmethod
    def _serve(value):
        if isinstance(value, Exception):
            raise value
        return value
