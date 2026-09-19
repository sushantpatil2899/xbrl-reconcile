"""HTTP client that identifies itself, paces requests and retries transient errors."""

import gzip
import time
import urllib.error
import urllib.request

RETRY_STATUS = {429, 500, 502, 503, 504}
TIMEOUT_SECONDS = 30


class HttpError(RuntimeError):
    """A request failed with a non retryable status or ran out of attempts."""


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        max_per_second: float = 5.0,
        max_attempts: int = 4,
        backoff_seconds: float = 1.0,
        opener=urllib.request.urlopen,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self._user_agent = user_agent
        self._min_interval = 1.0 / max_per_second
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._opener = opener
        self._sleep = sleep
        self._clock = clock
        self._last_request_at = None

    def get(self, url: str) -> bytes:
        """Return the response body, decompressed if the server sent gzip."""
        request = urllib.request.Request(
            url, headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip"}
        )
        for attempt in range(1, self._max_attempts + 1):
            self._wait_for_slot()
            try:
                with self._opener(request, timeout=TIMEOUT_SECONDS) as response:
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as err:
                # HTTPError is a subclass of URLError, so it must be caught first.
                if err.code not in RETRY_STATUS or attempt == self._max_attempts:
                    raise HttpError(f"GET {url} failed with status {err.code}") from err
            except urllib.error.URLError as err:
                if attempt == self._max_attempts:
                    raise HttpError(f"GET {url} failed: {err.reason}") from err
            self._sleep(self._backoff_seconds * 2 ** (attempt - 1))
        raise HttpError(f"GET {url} failed")

    def _wait_for_slot(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_request_at = self._clock()
