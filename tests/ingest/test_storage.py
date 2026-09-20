import io
from types import SimpleNamespace

from xbrl_reconcile.ingest.storage import (
    STATE_KEY,
    LocalStorage,
    S3Storage,
    make_s3_client,
    region_from_endpoint,
    snapshot_key,
)


class NoSuchKey(Exception):
    pass


class FakeS3Client:
    exceptions = SimpleNamespace(NoSuchKey=NoSuchKey)

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise NoSuchKey(Key)
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


def test_snapshot_key_layout():
    key = snapshot_key("companyfacts", "0001108524", "2026-09-16T061502Z")
    assert key == "raw/sec/companyfacts/cik=0001108524/2026-09-16T061502Z.json.gz"


def test_state_key_layout():
    assert STATE_KEY == "raw/sec/_state/last_seen.json"


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.write("raw/sec/a/b.json.gz", b"data")
    assert (tmp_path / "raw/sec/a/b.json.gz").read_bytes() == b"data"
    assert storage.read("raw/sec/a/b.json.gz") == b"data"


def test_local_storage_missing_key_returns_none(tmp_path):
    assert LocalStorage(tmp_path).read("nope") is None


def test_s3_storage_round_trip():
    client = FakeS3Client()
    storage = S3Storage("bucket", client)
    storage.write("k", b"data")
    assert client.objects[("bucket", "k")] == b"data"
    assert storage.read("k") == b"data"


def test_s3_storage_missing_key_returns_none():
    assert S3Storage("bucket", FakeS3Client()).read("nope") is None


def test_region_from_b2_endpoint():
    assert region_from_endpoint("https://s3.us-west-004.backblazeb2.com") == "us-west-004"


def test_make_s3_client_uses_endpoint_without_network():
    client = make_s3_client("https://s3.us-west-004.backblazeb2.com", "id", "secret")
    assert client.meta.endpoint_url == "https://s3.us-west-004.backblazeb2.com"
    assert client.meta.region_name == "us-west-004"
