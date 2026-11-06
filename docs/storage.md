# Storage

[← back to the README](../README.md)

## What this does

One Backblaze B2 bucket holds everything the pipeline persists, in two zones: a
raw zone nothing ever rewrites, and a warehouse zone the transform step
republishes on every run. There is no database server. DuckDB reads the raw
layer over S3 in place, builds a file, and that file goes back to the bucket.

## How it works

```
raw/sec/<dataset>/cik=<cik10>/<run_ts>.json.gz    companyfacts and submissions
raw/fsds/...                                      quarterly Financial Statement Data Sets
raw/linkbase/cik=<cik10>/<accession>/<name>       calculation linkbase XML
raw/config/<name>/<run_ts>.json                   the config in force at that run
raw/sec/_state/last_seen.json                     what ingestion has already seen

warehouse/xbrl.duckdb                             the built database, gzipped
warehouse/parquet/mart_*.parquet                  the twelve published marts
warehouse/parquet/_index.json                     row count and byte size of each
```

The raw prefixes are append only by convention and by key design: every raw key
carries a UTC run timestamp, so a second write lands beside the first rather
than over it. The warehouse keys are fixed, so each run replaces the previous
build.

**`_index.json` is the version marker.** It records the row count and byte size
of every mart. The fetch helper checks each downloaded file against it, so a
truncated download fails at fetch time rather than being served. The static page
uses the same file as a cache key, described in [page.md](page.md).

**The database is stored gzipped.** A 92 MB DuckDB file compresses well, and the
runner that rebuilds it is wiped after every run, so the download and upload
happen on every single transform.

## Decisions worth knowing

**Backblaze has two APIs and they do not take the same credentials.** This cost
real time, so it is worth stating plainly. The Terraform `b2` provider speaks
the B2 native API, whose master key ID is twelve characters. Everything else
here, this project's own code and DuckDB's `httpfs`, speaks the S3 compatible
API, which rejects the master application key outright with
`InvalidAccessKeyId: Malformed Access Key Id`, before any permission is checked.
The S3 API needs a key created under Account, Application Keys, whose ID is
around twenty five characters. Terraform creates exactly such a scoped key for
the pipeline, limited to this bucket and unable to delete anything.

**Parquet rather than a served database.** The twelve marts are 1,397 KB
together against a 92 MB database. Because Parquet supports range requests, a
reader fetches only the byte ranges a query needs: an income statement costs
about 100 KB and no server at all. That is what makes both the API container and
the browser page possible without a warehouse behind either.

## Run it yourself

To read the published database locally, create a read only key limited to the
bucket, then:

```bash
export STORAGE_BACKEND=b2 B2_BUCKET=<bucket> B2_ENDPOINT=https://s3.<region>.backblazeb2.com
export B2_INGEST_KEY_ID=<key id> B2_INGEST_KEY=<key>
WAREHOUSE_PATH=transform/prod.duckdb uv run xbrl-fetch-warehouse
```

To fetch just the marts, which need no credentials at all once published:

```bash
MARTS_PATH=./marts uv run xbrl-fetch-marts
```

## Verify

The marts are public, so the index and any single table can be read directly:

```bash
curl -s https://sushantpatil2899.github.io/xbrl-reconcile/_index.json
```

DuckDB can query one over HTTP without downloading the whole file:

```sql
select count(*) from 'https://sushantpatil2899.github.io/xbrl-reconcile/mart_financials.parquet';
```

## Deeper

Section 7.4 of [design.md](design.md) describes the raw layout, 7.5 the local
and B2 storage modes, 14.3 the compression decision, and 15.13 the range request
behaviour measured rather than assumed.
