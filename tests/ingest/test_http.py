import gzip
import urllib.error

import pytest

from tests.ingest.fakes import FakeClock, FakeOpener, FakeResponse, http_error
from xbrl_reconcile.ingest.http import HttpError, PoliteClient


def make_client(outcomes, **kwargs):
    opener = FakeOpener(outcomes)
    clock = FakeClock()
    client = PoliteClient(
        user_agent="xbrl-reconcile test@example.org",
        opener=opener,
        sleep=clock.sleep,
        clock=clock.time,
        **kwargs,
    )
    return client, opener, clock


def test_sends_user_agent_and_accepts_gzip():
    client, opener, _ = make_client([FakeResponse(b"{}")])
    client.get("https://example.test/a.json")
    request = opener.requests[0]
    assert request.get_header("User-agent") == "xbrl-reconcile test@example.org"
    assert request.get_header("Accept-encoding") == "gzip"


def test_returns_plain_body():
    client, _, _ = make_client([FakeResponse(b'{"a": 1}')])
    assert client.get("https://example.test/a.json") == b'{"a": 1}'


def test_decompresses_gzip_body():
    body = gzip.compress(b'{"a": 1}')
    client, _, _ = make_client([FakeResponse(body, {"Content-Encoding": "gzip"})])
    assert client.get("https://example.test/a.json") == b'{"a": 1}'


def test_retries_server_error_then_succeeds():
    client, opener, clock = make_client([http_error(503), FakeResponse(b"ok")], max_per_second=1000)
    assert client.get("https://example.test/a.json") == b"ok"
    assert len(opener.requests) == 2
    assert 1.0 in clock.sleeps


def test_retries_network_error_then_succeeds():
    client, opener, _ = make_client(
        [urllib.error.URLError("reset"), FakeResponse(b"ok")], max_per_second=1000
    )
    assert client.get("https://example.test/a.json") == b"ok"
    assert len(opener.requests) == 2


def test_does_not_retry_not_found():
    client, opener, _ = make_client([http_error(404)])
    with pytest.raises(HttpError, match="404"):
        client.get("https://example.test/a.json")
    assert len(opener.requests) == 1


def test_gives_up_after_max_attempts():
    client, opener, _ = make_client([http_error(429)] * 3, max_attempts=3, max_per_second=1000)
    with pytest.raises(HttpError, match="429"):
        client.get("https://example.test/a.json")
    assert len(opener.requests) == 3


def test_backoff_doubles_each_attempt():
    client, _, clock = make_client(
        [http_error(500), http_error(500), FakeResponse(b"ok")], max_per_second=1000
    )
    client.get("https://example.test/a.json")
    backoffs = [s for s in clock.sleeps if s >= 1.0]
    assert backoffs == [1.0, 2.0]


def test_paces_requests_to_max_per_second():
    client, _, clock = make_client([FakeResponse(b"1"), FakeResponse(b"2")], max_per_second=5)
    client.get("https://example.test/1")
    client.get("https://example.test/2")
    assert clock.sleeps == [pytest.approx(0.2)]
