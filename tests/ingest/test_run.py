import gzip
import json
from datetime import UTC, datetime

import pytest

from tests.ingest.fakes import FakeSecApi, submissions_json
from xbrl_reconcile.config import Company, ConfigError
from xbrl_reconcile.ingest.http import HttpError
from xbrl_reconcile.ingest.run import build_storage, run_ingestion
from xbrl_reconcile.ingest.storage import STATE_KEY, LocalStorage, S3Storage, config_snapshot_key
from xbrl_reconcile.mappings import parse_mappings

MORNING = datetime(2026, 9, 16, 6, 15, 2, tzinfo=UTC)
AFTERNOON = datetime(2026, 9, 16, 14, 0, 0, tzinfo=UTC)


def company(cik, ticker, enabled=True, report_types=("10-K", "10-Q")):
    return Company(
        cik=cik,
        ticker=ticker,
        name=ticker,
        start_year=2009,
        end_year=None,
        enabled=enabled,
        report_types=report_types,
    )


def keys(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_first_run_downloads_and_writes_state(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b'{"facts": {}}'},
    )
    storage = LocalStorage(tmp_path)

    result = run_ingestion([company(1, "AAA")], api, storage, MORNING)

    assert result.downloaded == ["AAA"]
    assert keys(tmp_path) == [
        "raw/config/companies/2026-09-16T061502Z.json",
        "raw/sec/_state/last_seen.json",
        "raw/sec/companyfacts/cik=0000000001/2026-09-16T061502Z.json.gz",
        "raw/sec/submissions/cik=0000000001/2026-09-16T061502Z.json.gz",
    ]
    stored = storage.read("raw/sec/companyfacts/cik=0000000001/2026-09-16T061502Z.json.gz")
    assert gzip.decompress(stored) == b'{"facts": {}}'
    state = json.loads(storage.read(STATE_KEY))
    assert state["last_run"] == "2026-09-16T061502Z"
    assert state["companies"]["0000000001"] == {
        "ticker": "AAA",
        "accession": "acc-1",
        "snapshot": "2026-09-16T061502Z",
    }


def test_second_run_without_new_report_skips(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)
    run_ingestion([company(1, "AAA")], api, storage, MORNING)

    result = run_ingestion([company(1, "AAA")], api, storage, AFTERNOON)

    assert result.skipped == ["AAA"]
    assert result.downloaded == []
    assert api.calls.count(("companyfacts", "0000000001")) == 1


def test_new_report_same_day_creates_second_snapshot(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)
    run_ingestion([company(1, "AAA")], api, storage, MORNING)

    api.submissions_by_cik["0000000001"] = submissions_json(
        [("10-Q/A", "acc-2", "2026-09-16"), ("10-Q", "acc-1", "2026-09-01")]
    )
    api.companyfacts_by_cik["0000000001"] = b'{"v": 2}'
    amended = company(1, "AAA", report_types=("10-Q", "10-Q/A"))

    result = run_ingestion([amended], api, storage, AFTERNOON)

    assert result.downloaded == ["AAA"]
    facts = [k for k in keys(tmp_path) if "companyfacts" in k]
    assert facts == [
        "raw/sec/companyfacts/cik=0000000001/2026-09-16T061502Z.json.gz",
        "raw/sec/companyfacts/cik=0000000001/2026-09-16T140000Z.json.gz",
    ]


def test_one_company_failing_does_not_stop_others(tmp_path):
    api = FakeSecApi(
        submissions={
            "0000000001": HttpError("GET failed with status 404"),
            "0000000002": submissions_json([("10-K", "acc-b", "2026-03-01")]),
        },
        companyfacts={"0000000002": b"{}"},
    )
    storage = LocalStorage(tmp_path)

    result = run_ingestion([company(1, "AAA"), company(2, "BBB")], api, storage, MORNING)

    assert result.downloaded == ["BBB"]
    assert "404" in result.failed["AAA"]
    assert "0000000001" not in json.loads(storage.read(STATE_KEY))["companies"]


def test_disabled_company_is_not_fetched(tmp_path):
    api = FakeSecApi()
    result = run_ingestion([company(1, "AAA", enabled=False)], api, LocalStorage(tmp_path), MORNING)
    assert api.calls == []
    assert result.downloaded == result.skipped == []


def test_build_storage_defaults_to_local(tmp_path):
    storage = build_storage({"LOCAL_DATA_DIR": str(tmp_path)})
    assert isinstance(storage, LocalStorage)


def test_build_storage_b2():
    storage = build_storage(
        {
            "STORAGE_BACKEND": "b2",
            "B2_BUCKET": "bucket",
            "B2_ENDPOINT": "https://s3.us-west-004.backblazeb2.com",
            "B2_INGEST_KEY_ID": "id",
            "B2_INGEST_KEY": "secret",
        }
    )
    assert isinstance(storage, S3Storage)


def test_build_storage_b2_missing_variable():
    with pytest.raises(ValueError, match="B2_BUCKET"):
        build_storage({"STORAGE_BACKEND": "b2"})


def test_build_storage_unknown_backend():
    with pytest.raises(ValueError, match="ftp"):
        build_storage({"STORAGE_BACKEND": "ftp"})


def test_config_snapshot_records_the_company_list(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)

    run_ingestion([company(1, "AAA")], api, storage, MORNING)

    rows = json.loads(storage.read(config_snapshot_key("companies", "2026-09-16T061502Z")))
    assert rows == [
        {
            "cik": 1,
            "cik10": "0000000001",
            "ticker": "AAA",
            "name": "AAA",
            "description": "",
            "group_name": "",
            "start_year": 2009,
            "end_year": None,
            "enabled": True,
        }
    ]


def test_config_snapshot_is_written_even_when_nothing_downloads(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)
    run_ingestion([company(1, "AAA")], api, storage, MORNING)

    result = run_ingestion([company(1, "AAA")], api, storage, AFTERNOON)

    assert result.skipped == ["AAA"]
    assert storage.read(config_snapshot_key("companies", "2026-09-16T140000Z")) is not None


def test_disabled_companies_are_recorded_with_enabled_false(tmp_path):
    storage = LocalStorage(tmp_path)
    companies = [company(1, "AAA", enabled=False), company(2, "BBB", enabled=False)]

    run_ingestion(companies, FakeSecApi(), storage, MORNING)

    rows = json.loads(storage.read(config_snapshot_key("companies", "2026-09-16T061502Z")))
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]
    assert [r["enabled"] for r in rows] == [False, False]


def test_heartbeat_updates_even_when_everything_is_skipped(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)
    run_ingestion([company(1, "AAA")], api, storage, MORNING)

    result = run_ingestion([company(1, "AAA")], api, storage, AFTERNOON)

    assert result.skipped == ["AAA"]
    state = json.loads(storage.read(STATE_KEY))
    assert state["last_run"] == "2026-09-16T140000Z"
    assert state["companies"]["0000000001"]["snapshot"] == "2026-09-16T061502Z"


def test_state_written_before_the_heartbeat_existed_is_still_understood(tmp_path):
    """The old state file had companies at the top level and no last_run."""
    storage = LocalStorage(tmp_path)
    old_shape = {"0000000001": {"ticker": "AAA", "accession": "acc-1", "snapshot": "old"}}
    storage.write(STATE_KEY, json.dumps(old_shape).encode())
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )

    result = run_ingestion([company(1, "AAA")], api, storage, MORNING)

    # Nothing re-downloaded, because the old accession was still recognised.
    assert result.skipped == ["AAA"]
    assert api.calls == [("submissions", "0000000001")]
    state = json.loads(storage.read(STATE_KEY))
    assert state["last_run"] == "2026-09-16T061502Z"
    assert state["companies"]["0000000001"]["accession"] == "acc-1"


MAPPINGS = parse_mappings(
    {
        "concepts": {
            "revenue": {
                "statement": "income_statement",
                "unit": "USD",
                "tags": [{"tag": "us-gaap:Revenues", "confidence": "high"}],
            }
        },
        "company_overrides": [
            {"cik": 1, "concept": "revenue", "ignore": ["us-gaap:SalesRevenueServicesNet"]}
        ],
    }
)


def test_mapping_snapshots_record_concepts_and_overrides(tmp_path):
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)

    run_ingestion([company(1, "AAA")], api, storage, MORNING, mappings=MAPPINGS)

    concepts = json.loads(storage.read(config_snapshot_key("tag_mappings", "2026-09-16T061502Z")))
    assert concepts == [
        {
            "concept": "revenue",
            "statement": "income_statement",
            "unit": "USD",
            "is_optional": False,
            "taxonomy": "us-gaap",
            "tag": "Revenues",
            "priority": 10,
            "confidence": "high",
            "note": "",
        }
    ]
    overrides = json.loads(
        storage.read(config_snapshot_key("tag_mapping_overrides", "2026-09-16T061502Z"))
    )
    assert overrides[0]["mode"] == "ignore"
    assert overrides[0]["tag"] == "SalesRevenueServicesNet"
    # Component sets are snapshotted too, even when empty for this config.
    assert (
        json.loads(storage.read(config_snapshot_key("tag_components", "2026-09-16T061502Z"))) == []
    )


def test_mapping_snapshots_are_skipped_when_no_mappings_are_given(tmp_path):
    """Ingestion still works without a mapping config, for example before Phase 3."""
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )
    storage = LocalStorage(tmp_path)

    run_ingestion([company(1, "AAA")], api, storage, MORNING)

    assert storage.read(config_snapshot_key("tag_mappings", "2026-09-16T061502Z")) is None


def test_an_override_for_an_unknown_company_aborts_before_any_sec_request(tmp_path):
    bad = parse_mappings(
        {
            "concepts": {
                "revenue": {
                    "statement": "income_statement",
                    "unit": "USD",
                    "tags": [{"tag": "us-gaap:Revenues", "confidence": "high"}],
                }
            },
            "company_overrides": [{"cik": 999, "concept": "revenue", "ignore": ["us-gaap:X"]}],
        }
    )
    api = FakeSecApi(
        submissions={"0000000001": submissions_json([("10-Q", "acc-1", "2026-09-01")])},
        companyfacts={"0000000001": b"{}"},
    )

    with pytest.raises(ConfigError, match="999"):
        run_ingestion([company(1, "AAA")], api, LocalStorage(tmp_path), MORNING, mappings=bad)

    assert api.calls == []
