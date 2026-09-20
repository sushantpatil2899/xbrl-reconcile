"""Where raw files land: a local folder or S3 compatible object storage."""

from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import boto3
from botocore.config import Config

RAW_PREFIX = "raw/sec"
STATE_KEY = f"{RAW_PREFIX}/_state/last_seen.json"


class Storage(Protocol):
    def write(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes | None: ...


def snapshot_key(dataset: str, cik10: str, run_ts: str) -> str:
    return f"{RAW_PREFIX}/{dataset}/cik={cik10}/{run_ts}.json.gz"


class LocalStorage:
    def __init__(self, root: Path):
        self._root = Path(root)

    def write(self, key: str, data: bytes) -> None:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes | None:
        path = self._root / key
        return path.read_bytes() if path.exists() else None


class S3Storage:
    def __init__(self, bucket: str, client):
        self._bucket = bucket
        self._client = client

    def write(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def read(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey:
            return None
        return response["Body"].read()


def region_from_endpoint(endpoint_url: str) -> str:
    """B2 endpoints look like https://s3.<region>.backblazeb2.com."""
    return urlparse(endpoint_url).hostname.split(".")[1]


def make_s3_client(endpoint_url: str, key_id: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_from_endpoint(endpoint_url),
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        # Newer boto3 adds checksum headers by default; only send them when required
        # so S3 compatible services that lack full support keep working.
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
