"""Filter one quarter of SEC's Financial Statement Data Sets to our companies.

These quarterly sets carry what the companyfacts JSON drops: facts broken down
by dimension, and company specific custom tags. One quarter is 600 MB of facts
across every US filer, of which our companies are about 1 MB, so each quarter is
filtered before anything is stored.

Filtering is by company only. The rows that survive are the bytes SEC published,
unparsed and unreformatted, so the raw layer stays faithful. Lines are matched on
raw bytes rather than decoded text, because company names in sub.txt contain
bytes that are not valid UTF-8.

The four files relate through `adsh`, the accession number of a filing, and only
sub.txt knows which company an adsh belongs to. So the passes run in order: read
sub.txt to learn our filings, stream num.txt and pre.txt keeping those filings,
then stream tag.txt keeping the definitions of the tags we actually kept.
"""

import gzip
import io
import json
import zipfile

DATASET_ROOT = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
FSDS_PREFIX = "raw/fsds"

# SEC's first published set. Asking for anything earlier returns 404 forever, so
# candidates are floored here rather than reported as not published yet on every
# run.
EARLIEST_QUARTER = "2009q2"

# The order here is the order the passes must run in.
DATASET_FILES = ("sub", "num", "pre", "tag")


def dataset_url(quarter: str) -> str:
    return f"{DATASET_ROOT}/{quarter}.zip"


def quarter_key(quarter: str, name: str) -> str:
    """A quarter is never revised by SEC, so the quarter itself is the version."""
    if name == "_filtered_for":
        return f"{FSDS_PREFIX}/{quarter}/_filtered_for.json"
    return f"{FSDS_PREFIX}/{quarter}/{name}.tsv.gz"


def quarters_between(first_year: int, last_year: int) -> list[str]:
    """Quarters in order, never earlier than SEC's first published set."""
    quarters = [f"{year}q{q}" for year in range(first_year, last_year + 1) for q in (1, 2, 3, 4)]
    return [q for q in quarters if q >= EARLIEST_QUARTER]


def filter_quarter(zip_bytes: bytes, ciks: set[int]) -> dict[str, bytes]:
    """Return the four files filtered to `ciks`, gzipped, plus a record of the filter."""
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    for name in DATASET_FILES:
        if f"{name}.txt" not in archive.namelist():
            raise ValueError(f"{name}.txt missing from the quarter archive")

    wanted_ciks = {str(cik).encode() for cik in ciks}
    our_filings: set[bytes] = set()
    kept_tags: set[tuple[bytes, bytes]] = set()
    output: dict[str, bytes] = {}
    fact_count = 0

    # sub.txt: the only file that maps a filing to a company.
    sub_lines, header = [], None
    for index, line in _stream(archive, "sub.txt"):
        if index == 0:
            header = _columns(line)
            sub_lines.append(line)
            continue
        fields = line.split(b"\t")
        if fields[header[b"cik"]] in wanted_ciks:
            our_filings.add(fields[header[b"adsh"]])
            sub_lines.append(line)
    output["sub"] = _gzip(sub_lines)

    # num.txt: the facts. Also collects which tag definitions we will need.
    num_lines, header = [], None
    for index, line in _stream(archive, "num.txt"):
        if index == 0:
            header = _columns(line)
            num_lines.append(line)
            continue
        fields = line.split(b"\t")
        if fields[header[b"adsh"]] in our_filings:
            num_lines.append(line)
            kept_tags.add((fields[header[b"tag"]], fields[header[b"version"]]))
            fact_count += 1
    output["num"] = _gzip(num_lines)

    # pre.txt: which statement and line each tag appears on.
    pre_lines, header = [], None
    for index, line in _stream(archive, "pre.txt"):
        if index == 0:
            header = _columns(line)
            pre_lines.append(line)
            continue
        fields = line.split(b"\t")
        if fields[header[b"adsh"]] in our_filings:
            pre_lines.append(line)
    output["pre"] = _gzip(pre_lines)

    # tag.txt: definitions, including the custom flag. Keyed by tag and version,
    # not by filing, so it is filtered to the tags the facts above used.
    tag_lines, header = [], None
    for index, line in _stream(archive, "tag.txt"):
        if index == 0:
            header = _columns(line)
            tag_lines.append(line)
            continue
        fields = line.split(b"\t")
        if (fields[header[b"tag"]], fields[header[b"version"]]) in kept_tags:
            tag_lines.append(line)
    output["tag"] = _gzip(tag_lines)

    # Recorded so a later run can tell which companies a stored quarter covers,
    # and re-fetch it when a company is added whose history it should include.
    output["_filtered_for"] = json.dumps(
        {
            "ciks": sorted(ciks),
            "filings": len(our_filings),
            "facts": fact_count,
        },
        indent=2,
    ).encode()
    return output


def _stream(archive: zipfile.ZipFile, name: str):
    """Yield (index, line) without holding the whole member in memory."""
    with archive.open(name) as handle:
        for index, line in enumerate(handle):
            stripped = line.rstrip(b"\r\n")
            if stripped:
                yield index, stripped


def _columns(header_line: bytes) -> dict[bytes, int]:
    """Column positions by name, so an added column cannot shift a field."""
    return {name: position for position, name in enumerate(header_line.split(b"\t"))}


def _gzip(lines: list[bytes]) -> bytes:
    return gzip.compress(b"\n".join(lines) + b"\n", mtime=0)
