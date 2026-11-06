# Ingestion

[← back to the README](../README.md)

## What this does

Pulls filings from three SEC sources and lands them in object storage exactly as
received. Nothing is reshaped, renamed or filtered on the way in. The raw layer
is the audit trail: if a later transformation turns out to be wrong, the
original bytes are still there to rebuild from.

## How it works

Three entry points, three schedules, three SEC sources.

| Command | Source | Schedule | Why that rhythm |
|---|---|---|---|
| `xbrl-ingest` | `data.sec.gov` companyfacts and submissions | daily, 06:00 UTC | A company files roughly four times a year, but you cannot know which day |
| `xbrl-ingest-datasets` | SEC DERA Financial Statement Data Sets | monthly, 5th | SEC publishes a quarter about six weeks after it ends |
| `xbrl-ingest-linkbase` | the filing archive on `www.sec.gov` | monthly, 6th | A filing is immutable once accepted, so its linkbase is fetched once and never again |

All three are idempotent. A quarter already landed is skipped, a linkbase
already fetched is skipped, and a filing already seen does not trigger a
rewrite. A day with no new filings does almost no work.

**Why three sources and not one.** The JSON API is the obvious one and it is not
enough. It silently drops every fact that carries a dimension, and for some
companies the number you want only exists as a dimensional fact. Workday never
tags a total cost of revenue; it reports the figure split by product line, and
the API returns none of those splits. The quarterly Data Sets carry them. The
calculation linkbases are a third source again, because they hold the filer's
own declared arithmetic, which is what [evidence.md](evidence.md) is built on.

**SEC etiquette is enforced in code, not in a comment.** `PoliteClient` sends a
`User-Agent` carrying a contact address, paces itself to five requests a second,
and retries `429`, `500`, `502`, `503` and `504` with exponential backoff, four
attempts, thirty second timeout. The contact address comes from
`SEC_CONTACT_EMAIL` and the process refuses to start without it, so an anonymous
run is not possible by accident.

**Failure is separated by cause.** A broken transformation stops the pipeline. One
company's odd data is quarantined and the other twenty seven publish. Ingestion
reports failure if any single company failed, and the `transform` workflow runs
anyway, because the companies that did land should still be transformed. A
genuinely stalled pipeline is caught by the freshness tests instead, which
measure a heartbeat rather than data age. Companies file about four times a
year, so a quiet fortnight is normal and must not page anyone.

**Config is snapshotted with the data.** `xbrl-snapshot-config` writes the
companies, mappings and vocabularies into `raw/config/` alongside the filings.
A rebuild from an old snapshot therefore uses the config that was in force at the
time, not today's.

## Decisions worth knowing

**Raw snapshots are written once and never overwritten.** Each carries a UTC
timestamp in its key, so an earlier view of the data is always recoverable. This
costs storage and buys the ability to answer "what did we think last March".

**Only new snapshots are processed.** The staging table records which files it
has already read in its own `source_file` column, so a quiet day reads nothing.
Before this, a run read 535 files and 92 MB; now a quiet day costs a single
15 MB download.

## Run it yourself

```bash
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-check-ciks
```

Verifies the CIKs in config against SEC, and needs no storage credentials.

Full ingestion needs a Backblaze bucket and a scoped key. See
[storage.md](storage.md) for how those are created and why the master key will
not work.

```bash
export STORAGE_BACKEND=b2 B2_BUCKET=<bucket> B2_ENDPOINT=https://s3.<region>.backblazeb2.com
export B2_INGEST_KEY_ID=<key id> B2_INGEST_KEY=<key>
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-ingest
```

`STORAGE_BACKEND=local` writes to a directory instead, which is enough to try
the pipeline without an account.

## Verify

The published data states when it was last refreshed, so the schedule is
checkable from the outside:

```bash
curl -s https://sushantpatil2899.github.io/xbrl-reconcile/_index.json | head -3
```

## Deeper

Section 7.2 of [design.md](design.md) covers the run flow, 7.3 SEC etiquette and
error handling, 11.3 the Data Sets ingestion, 13.2 the linkbase fetch, and 14.2
how incremental staging cut the daily cost.
