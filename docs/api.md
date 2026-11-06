# The API

[← back to the README](../README.md)

**Live:** https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io
· [`/docs`](https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/docs)
· [`/redoc`](https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/redoc)

## What this does

FastAPI over the Parquet marts. Eleven routes, no database behind it: the marts
are baked into the container image, so the process reads local files and the
whole thing scales to zero between requests.

| Route | Answers |
|---|---|
| `/` | What is in here, and when it was last refreshed |
| `/healthz` | Is it up, and against which data |
| `/companies` | The 28 companies |
| `/concepts` | The 16 canonical concepts, with their statement and unit |
| `/vocabularies` | Every value the API can return, with what each means |
| `/financials` | The facts, filtered by ticker, concept, period, year, confidence, evidence |
| `/statements/{statement}` | An income statement, balance sheet or cash flow laid out as a statement |
| `/confidence` | What a statement is made of, and whether to trust it |
| `/coverage` | What is mapped and what is not |
| `/evidence/{kind}` | What the filings' own arithmetic says |
| `/tags/{kind}` | Custom and unmapped tags |

## How it works

**Documentation is generated from config.** Every parameter's allowed values and
their meanings come from `config/vocabularies.yml`. Adding a concept or a
company changes the OpenAPI document with no code change, and a value cannot be
returned without an explanation of it existing somewhere a caller can read.

**Every response carries its own provenance.** `as_of` says which build answered,
`filters_applied` echoes what the server actually did with your query including
defaults you did not set, and `pagination` carries the total and a `next` link.

```bash
curl -s 'https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/financials?tickers=CRWD&concepts=revenue&period=annual&from_year=2024&to_year=2024'
```

```json
{
  "ticker": "CRWD",
  "concept": "revenue",
  "value": 3953624000.0,
  "unit": "USD",
  "period_end": "2025-01-31",
  "fiscal_year": 2025,
  "calendar_year_equivalent": 2024,
  "confidence": "high",
  "source_tag": "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
  "evidence": "confirmed",
  "basis": "us_gaap",
  "form": "10-K"
}
```

That one row shows most of the project. CrowdStrike is the only company here
using the `IncludingAssessedTax` variant, so a query written against the common
tag returns nothing for it. Its fiscal 2025 is calendar 2024, so a year range
needs to say which label it means. And the value carries both its confidence
and the verdict of CrowdStrike's own declared arithmetic.

**A typo is an error, not an empty answer.**

```bash
curl -s '.../financials?tickers=GOOGL'   # 400
```

```json
{
  "error": "unknown ticker: 'GOOGL'",
  "field": "ticker",
  "value": "GOOGL",
  "valid": ["ADBE", "ADSK", "BOX", "CRM", "CRWD", "DDOG", "..."]
}
```

An empty result would be indistinguishable from a company that filed nothing.

## Decisions worth knowing

**The app is built by a factory, not at import time.** Opening the marts is file
I/O, and doing it during module import would make every test that imports the
app depend on a directory of Parquet existing. The serving entry point in
`asgi.py` opens them and fails fast: a process with no data to serve should
refuse to start rather than answer nothing.

**The rate limiter keys on the caller's address**, which is why
`FORWARDED_ALLOW_IPS` matters. uvicorn trusts `X-Forwarded-For` only from
`127.0.0.1` by default, so behind a managed ingress every request appears to
come from the proxy and all callers land in one bucket. Set it to the proxy's
address. `*` trusts the header from whoever sent it, so use it only when nothing
but the proxy can reach the port.

**It can state its own gaps.** `GET /coverage?status=missing` currently returns
zero rows out of 5,056, and `GET /confidence?trust=check` returns 26 of the 632
annual statements. An API that answers "where are you weak" is a stronger claim
than one that cannot be asked.

**When not to use it.** For the whole dataset rather than an answer, read the
Parquet directly. DuckDB fetches only the byte ranges it needs, so this costs a
few kilobytes of a 737 KB file and no server at all:

```sql
select ticker, fiscal_year, value, confidence
from 'https://sushantpatil2899.github.io/xbrl-reconcile/mart_financials.parquet'
where concept = 'revenue' and period_kind = 'annual';
```

## Run it yourself

Needs nothing but the published Parquet, about 1.4 MB:

```bash
MARTS_PATH=./marts uv run xbrl-fetch-marts
```

```bash
MARTS_PATH=./marts uv run uvicorn xbrl_reconcile.api.asgi:app --port 8000
```

Or in a container with the data baked in, so it needs no credentials to run:

```bash
docker build --secret id=b2_key_id,env=B2_INGEST_KEY_ID --secret id=b2_key,env=B2_INGEST_KEY -t xbrl-reconcile .
```

## Verify

```bash
curl -s https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/healthz
```

The `as_of` it returns should match `published_at` in
[`_index.json`](https://sushantpatil2899.github.io/xbrl-reconcile/_index.json).
If they differ, the API is serving an older build than the page.

## Deeper

Section 15 of [design.md](design.md) is the API as built: 15.2 the layers, 15.4
documentation generated from config, 15.6 pagination, 15.7 logging and the
limiter, 15.8 the proxy trap, and 15.9 the container.
