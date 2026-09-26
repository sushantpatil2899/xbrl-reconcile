import gzip
import io
import json
import zipfile

import pytest

from xbrl_reconcile.ingest.datasets import (
    DATASET_FILES,
    dataset_url,
    filter_quarter,
    quarter_key,
    quarters_between,
)

# Two of our filings and one from another company, in SEC's tab separated shape.
SUB = (
    b"adsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\tdetail\n"
    b"0001327811-26-000026\t1327811\tWorkday\t10-Q\t20260430\t2026\tQ1\t20260528\t1\n"
    b"0000896878-26-000025\t896878\tIntuit\t10-Q\t20260430\t2026\tQ3\t20260521\t1\n"
    b"0000320193-26-000001\t320193\tApple Inc\xae\t10-Q\t20260331\t2026\tQ2\t20260501\t1\n"
)
NUM = (
    b"adsh\ttag\tversion\tddate\tqtrs\tuom\tsegments\tcoreg\tvalue\tfootnote\n"
    b"0001327811-26-000026\tCostOfGoodsAndServicesSold\tus-gaap/2025\t20260430\t1\tUSD\t"
    b"ProductOrService=SubscriptionServices;\t\t412000000.0000\t\n"
    b"0001327811-26-000026\tCostOfGoodsAndServicesSold\tus-gaap/2025\t20260430\t1\tUSD\t"
    b"ProductOrService=ProfessionalServices;\t\t192000000.0000\t\n"
    b"0001327811-26-000026\tRevenues\tus-gaap/2025\t20260430\t1\tUSD\t\t\t2411000000.0000\t\n"
    b"0000896878-26-000025\tCostOfRevenueSubscription\t0000896878-26-000025\t20260430\t1\tUSD\t\t\t99.0000\t\n"
    b"0000320193-26-000001\tRevenues\tus-gaap/2025\t20260331\t1\tUSD\t\t\t90000000000.0000\t\n"
)
TAG = (
    b"tag\tversion\tcustom\tabstract\tdatatype\tiord\tcrdr\ttlabel\tdoc\n"
    b"CostOfGoodsAndServicesSold\tus-gaap/2025\t0\t0\tmonetary\tD\tD\tCost of Revenue\tdoc\n"
    b"Revenues\tus-gaap/2025\t0\t0\tmonetary\tD\tC\tRevenues\tdoc\n"
    b"CostOfRevenueSubscription\t0000896878-26-000025\t1\t0\tmonetary\tD\tD"
    b"\tCost Of Revenue Subscription\tdoc\n"
    b"SomeoneElsesTag\tus-gaap/2025\t0\t0\tmonetary\tD\tD\tUnused here\tdoc\n"
)
PRE = (
    b"adsh\treport\tline\tstmt\tinpth\trfile\ttag\tversion\tplabel\tnegating\n"
    b"0001327811-26-000026\t2\t3\tIS\t0\tH\tRevenues\tus-gaap/2025\tRevenues\t0\n"
    b"0000320193-26-000001\t2\t3\tIS\t0\tH\tRevenues\tus-gaap/2025\tRevenues\t0\n"
)


def make_zip(sub=SUB, num=NUM, tag=TAG, pre=PRE) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("sub.txt", sub)
        z.writestr("num.txt", num)
        z.writestr("tag.txt", tag)
        z.writestr("pre.txt", pre)
        z.writestr("readme.htm", b"<html>ignored</html>")
    return buffer.getvalue()


def lines(files: dict[str, bytes], name: str) -> list[bytes]:
    return gzip.decompress(files[name]).splitlines()


def test_url_and_key_layout():
    assert dataset_url("2026q2") == (
        "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2026q2.zip"
    )
    assert quarter_key("2026q2", "num") == "raw/fsds/2026q2/num.tsv.gz"
    assert quarter_key("2026q2", "_filtered_for") == "raw/fsds/2026q2/_filtered_for.json"


def test_only_our_companies_are_kept():
    files = filter_quarter(make_zip(), {1327811, 896878})

    subs = lines(files, "sub")
    assert len(subs) == 3, "header plus our two filings"
    assert all(b"0000320193" not in line for line in subs)

    nums = lines(files, "num")
    assert len(nums) == 5, "header plus our four facts"
    assert all(b"0000320193" not in line for line in nums)


def test_headers_are_preserved():
    files = filter_quarter(make_zip(), {1327811})
    for name in DATASET_FILES:
        first = lines(files, name)[0]
        assert first.startswith(b"adsh") or first.startswith(b"tag")


def test_dimensional_rows_survive_untouched():
    files = filter_quarter(make_zip(), {1327811})
    nums = lines(files, "num")
    dimensional = [line for line in nums if b"ProductOrService" in line]
    assert len(dimensional) == 2
    assert b"ProductOrService=SubscriptionServices;" in dimensional[0]


def test_tag_definitions_are_filtered_to_the_tags_we_kept():
    files = filter_quarter(make_zip(), {896878})
    tags = lines(files, "tag")
    kept = [line.split(b"\t")[0] for line in tags[1:]]
    # Intuit's filing uses only its own custom tag here.
    assert kept == [b"CostOfRevenueSubscription"]
    assert all(b"SomeoneElsesTag" not in line for line in tags)


def test_non_utf8_bytes_are_preserved():
    """SEC company names contain bytes that are not valid UTF-8."""
    files = filter_quarter(make_zip(), {320193})
    assert b"Apple Inc\xae" in gzip.decompress(files["sub"])


def test_a_quarter_with_none_of_our_companies_yields_headers_only():
    files = filter_quarter(make_zip(), {1})
    for name in DATASET_FILES:
        assert len(lines(files, name)) == 1


def test_the_cik_list_is_recorded():
    files = filter_quarter(make_zip(), {1327811, 896878})
    recorded = json.loads(files["_filtered_for"])
    assert recorded["ciks"] == [896878, 1327811]
    assert recorded["filings"] == 2
    assert recorded["facts"] == 4


def test_columns_are_found_by_header_name_not_position():
    """An added column must not shift the meaning of a field."""
    sub = (
        b"extra\tadsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\tdetail\n"
        b"x\t0001327811-26-000026\t1327811\tWorkday\t10-Q\t20260430\t2026\tQ1\t20260528\t1\n"
    )
    num = (
        b"extra\tadsh\ttag\tversion\tddate\tqtrs\tuom\tsegments\tcoreg\tvalue\tfootnote\n"
        b"x\t0001327811-26-000026\tRevenues\tus-gaap/2025\t20260430\t1\tUSD\t\t\t1.0000\t\n"
    )
    files = filter_quarter(make_zip(sub=sub, num=num), {1327811})
    assert len(lines(files, "sub")) == 2
    assert len(lines(files, "num")) == 2


def test_a_missing_file_in_the_zip_is_an_error():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("sub.txt", SUB)
    with pytest.raises(ValueError, match="num.txt"):
        filter_quarter(buffer.getvalue(), {1327811})


def test_quarters_between_lists_quarters_in_order():
    assert quarters_between(2025, 2026) == [
        "2025q1",
        "2025q2",
        "2025q3",
        "2025q4",
        "2026q1",
        "2026q2",
        "2026q3",
        "2026q4",
    ]
