# xbrl-reconcile

[![ci](https://github.com/sushantpatil2899/xbrl-reconcile/actions/workflows/ci.yml/badge.svg)](https://github.com/sushantpatil2899/xbrl-reconcile/actions/workflows/ci.yml)

A data pipeline that ingests SEC XBRL filings for software companies and
reconciles inconsistent accounting tags into comparable financial statements,
with a confidence level on every mapped value.

## The problem

Since 2009, US public companies must tag every number in their financial
reports using XBRL, a machine readable vocabulary. In theory that makes company
comparison trivial. In practice the same concept is tagged differently by
different companies, and by the same company across years.

Measured across the 28 companies in this project:

- **2,047** distinct `us-gaap` concepts are in use. Only **42** are used by all
  28 companies, while **774** are used by exactly one.
- Revenue alone appears under at least five standard tags. Most companies use
  `RevenueFromContractWithCustomerExcludingAssessedTax`; CrowdStrike uses the
  **Including** variant. Intuit has used four different revenue tags over time.
- Companies restate. Salesforce reported total assets at 2018-01-31 as
  **$21,009,802,000** in its annual report, then **$21,984,000,000** three
  months later after an accounting rule change. Both numbers are correct in
  their moment.
- **113,249** of **226,028** company facts are reported by more than one
  filing, so any naive query returns duplicates.
- **A third of the facts are invisible in SEC's JSON API.** Workday never tags a
  total cost of revenue; it reports the figure split by product line, and that API
  drops every dimensional fact. Recovering them needs SEC's quarterly Financial
  Statement Data Sets, where 131,908 of 395,773 facts carry a dimension.

- **Not every filing that carries XBRL is a financial report.** Proxy statements
  tag net income in their pay versus performance table, often in millions and
  sometimes against the wrong year. A proxy is filed after the 10-K, so a naive
  "latest wins" rule publishes Elastic's 2025 net loss as $0.4 million instead of
  $108.1 million.

A query for "revenue" that assumes one tag silently returns nothing for
CrowdStrike, and silently returns the wrong year's version for Salesforce.
Resolving that is what this project does.

## Status

| Phase | State | What it does |
|---|---|---|
| 0. Foundation | Built | Python project, tests, lint, CI |
| 1. Ingestion | Built | Daily pull of SEC companyfacts and submissions into object storage |
| 2. Staging | Built | Flattens nested JSON into one row per fact, tested and published |
| 3. Mapping | Built | Maps raw tags to canonical concepts with confidence levels |
| 4. Data Sets | Built | Dimensional facts and custom tags from SEC's quarterly Data Sets |
| 5. Marts | Built | Comparable income statement, balance sheet, cash flow, confidence report |
| 6. Linkbase | Planned | Parse filing calculation linkbases to back high confidence mappings |
| 7. API | Planned | FastAPI over the marts |

Running today: three scheduled workflows, 293 dbt nodes and 143 Python tests,
408,213 facts from the JSON API plus 395,773 from the quarterly Data Sets, 16
canonical concepts with a confidence level on every value, and **25,326 published
figures** across 4,900 financial statements, at zero infrastructure cost.

The marts are published as Parquet: **1.15 MB for all eight**, against a 57 MB
database, so reading an income statement costs 101 KB and needs no warehouse.

```sql
select ticker, fiscal_year, revenue, gross_profit, gross_profit_confidence
from 'mart_income_statement.parquet'
where period_kind = 'annual' and calendar_year_equivalent = 2025
order by revenue desc
```

| ticker | fiscal_year | revenue | gross_profit | gross_profit_confidence |
|---|---|---|---|---|
| CRM | 2026 | 41,525 | 32,255 | high |
| ADBE | 2025 | 23,769 | 21,218 | high |
| INTU | 2025 | 18,831 | 15,139 | **derived** |
| NOW | 2025 | 13,278 | 10,295 | high |
| WDAY | 2026 | 9,552 | 7,231 | **derived** |

Four different fiscal year labels, one comparable year. Intuit and Workday never
tag gross profit at all, so theirs is computed from revenue and cost of revenue and
says so.

## Architecture

```mermaid
flowchart TD
    SEC[SEC EDGAR JSON APIs] -->|daily, only when a new report is filed| ING[Ingestion job]
    CFG[config/companies.yml] --> ING
    ING -->|raw snapshots, never modified| B2[(Backblaze B2)]
    B2 --> DBT[dbt + DuckDB]
    DBT -->|staging, then mapping, then marts| WH[(warehouse/xbrl.duckdb)]
    WH --> B2
    WH -->|8 marts as Parquet, 1.15 MB| PQ[(warehouse/parquet/)]
    PQ --> B2
    TF[Terraform] -.->|bucket, scoped key, CI secrets| B2
```

Both jobs run in GitHub Actions. Transform starts automatically when ingestion
finishes. The runner is wiped after each run, so the database is fetched from
storage, rebuilt, and published back.

## Design decisions

Full reasoning is in [docs/design.md](docs/design.md). The ones that shape
everything else:

- **Config drives the pipeline.** Adding a company is three lines of YAML. No
  ticker, CIK or tag name appears in code.
- **Raw data is never modified.** Snapshots are written once with a UTC
  timestamp and never overwritten, so an earlier view of the data is always
  recoverable.
- **Staging keeps every version of every fact.** Restatements are data, not
  noise, and deduplicating early would throw away the evidence.
- **Only new snapshots are processed.** The staging table's own `source_file`
  column records what has been handled, so a quiet day reads nothing.
- **Failures are separated by cause.** A broken transformation stops the
  pipeline; one company's odd data is quarantined and the other 27 publish.
- **Staleness is measured on a heartbeat**, not on data age, because companies
  file about four times a year and a quiet fortnight is normal.
- **A computed value is never dressed up as a reported one.** Totals recovered by
  summing a company's own components carry their own confidence level, and the
  identity used is recorded alongside the number.
- **Two year labels, because a fiscal year is not a calendar year.** Sixteen of
  these companies end their year in January, so one label spans 335 days. Every
  period carries what the company calls the year and the calendar year it lines up
  with, and no period is ever relabelled onto a quarter it did not report.
- **A statement is published twice over.** Each line carries its latest figure and
  the figure from one filing that reported the whole statement, because a company
  can restate one line of an old balance sheet and never re-publish the rest.
- **Statement layouts come from config.** The order concepts appear in
  `config/tag_mappings.yml` is the order they appear on the statement, and the
  columns are generated from it, so reordering a statement is a config edit.

## Running it

### Locally, without any credentials

```bash
uv sync
uv run pytest
```

To build the models against a local copy of the raw layer:

```bash
cd transform
RAW_ROOT=/path/to/raw uv run dbt build --profiles-dir . --target dev
```

### The full pipeline

Needs a Backblaze B2 account (free tier), an HCP Terraform account for state,
and a GitHub token. Terraform creates the bucket, a key scoped to it that
cannot delete files, and the repository secrets the workflows use:

```bash
cd infra/terraform
terraform init && terraform plan
```

Ingestion can also be run directly:

```bash
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-ingest      # SEC requires a contact
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-check-ciks  # verify config CIKs
```

## Layout

```
config/companies.yml        the 28 companies, date range, which forms count
src/xbrl_reconcile/
  config.py                 load and validate config
  mappings.py               load and validate the tag mapping config
  ingest/                   polite HTTP client, SEC endpoints, storage, run loop
  warehouse.py              fetch and publish the built database
  publish_marts.py          export the marts as Parquet
transform/
  models/staging/           one row per fact, typed, quarantining bad rows
  models/intermediate/      mapping, resolution, the period spine, derived values
  models/marts/             the published facts, three statements, two reports
  macros/                   snapshot selection, statement columns built from config
  tests/                    freshness, accounting identities, mart round trips
infra/terraform/            bucket, scoped key, Actions secrets and variables
.github/workflows/          ci, ingest, transform
docs/design.md              decisions and the reasoning behind them
```

## Data source

SEC's free [data.sec.gov](https://data.sec.gov) APIs. Requests identify
themselves with a contact email and stay within SEC's rate limits, as its
access policy requires.

## Author

Sushant Patil, [sushantpatil.me](https://www.sushantpatil.me)
