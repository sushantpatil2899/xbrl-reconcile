# xbrl-reconcile: Design

Status: Phase 0 and Phase 1 decided. Later phases list open decisions only.
Last updated: 2026-09-16

## 1. Goal

Pull XBRL financial data from SEC for a configured set of software companies,
map inconsistent tags to a standard set of concepts with a confidence label on
every value, and serve comparable financial statements through an API.

Constraints:

- Zero ongoing cost. Free forever tiers only; no student credits for anything
  the running pipeline depends on.
- Config drives everything. No ticker, CIK, tag name or year is hardcoded in
  code.
- Batch, not real time.

## 2. Background terms

| Term | Meaning |
|---|---|
| SEC | US regulator. Public companies must file reports with it. |
| 10-K / 10-Q | Yearly / quarterly report of a US company. |
| 20-F / 40-F | Yearly report of a foreign / Canadian company listed in the US. |
| US GAAP / IFRS | US and international accounting rulebooks. Each has its own tag set. |
| XBRL | Machine readable tags on every number in a report. Required 2009 to 2011 (phased by company size). |
| Inline XBRL | Newer style (about 2019 onward) where tags live inside the report itself. |
| CIK | SEC's permanent company ID. Never changes, unlike ticker or name. |
| Fiscal year end | The date a company's own accounting year ends. Not always Dec 31. |
| companyfacts | SEC JSON file per company holding every tagged fact from all its filings. |
| submissions | SEC JSON file per company listing its filings. |

## 3. Findings that shape the design

Verified against SEC data on 2026-09-16.

1. **companyfacts contains standard taxonomy tags only** (us-gaap, ifrs-full,
   dei, srt, ecd, ffd). Company specific custom tags (for example `crm:`) are
   not included. Custom tags must come from a second source (Phase 4).
2. **`fy` and `fp` on a fact describe the filing, not the period.** A 2016
   value appears with `fy: 2019` because it was repeated in the 2019 10-K.
   Periods must be derived from `start` and `end` dates.
3. **The same fact repeats** once per filing that reports it (original plus
   later comparatives or restatements).
4. **Most SEC filings are not financial reports.** Salesforce filed 172 items
   in the last year; only 4 were 10-K or 10-Q. Change detection must filter
   by report type.
5. **Atlassian has both IFRS and US GAAP facts** (20-F filer through 2022,
   10-K from 2023). Its XBRL data starts in 2018.
6. One compressed companyfacts file is about 0.35 MB (Salesforce).

## 4. Phase roadmap

| # | Phase | Output |
|---|---|---|
| 0 | Foundation | Repo layout, Python env, config, lint and tests in CI |
| 1 | Ingestion | companyfacts and submissions landed raw in Backblaze B2 daily; infra in Terraform |
| 2 | dbt staging | One clean row per fact, periods derived from dates |
| 3 | Mapping and intermediate | Tag mapping config, canonical values with confidence |
| 4 | Custom tags | SEC Financial Statement Data Sets filtered to our companies |
| 5 | Marts and tests | Income statement, balance sheet, cash flow, confidence report |
| 6 | Linkbase verification | Parse calculation linkbase to back high confidence mappings |
| 7 | API | FastAPI over the marts |
| 8 | Optional | Snowflake comparison, LocalStack AWS variant, frontend |

## 5. Company selection

Rules: primarily subscription software; a deliberate mix of ages, mergers,
renames, delisted companies, fiscal year ends and accounting rulebooks.

| Ticker | CIK | Name | Group | Why |
|---|---|---|---|---|
| ADBE | 796343 | Adobe | old_timer | XBRL since 2009; 52/53 week year ending near Nov 30 |
| INTU | 896878 | Intuit | old_timer | Acquired Credit Karma (2020), Mailchimp (2021); July year end |
| CRM | 1108524 | Salesforce | old_timer | Acquired Tableau (2019), Slack (2021); renamed 2022 |
| ADSK | 769397 | Autodesk | old_timer | Shift from licenses to subscriptions |
| WDAY | 1327811 | Workday | middle | Typical SaaS, January year end |
| NOW | 1373715 | ServiceNow | middle | Calendar year; renamed from Service-now.com |
| HUBS | 1404655 | HubSpot | middle | Calendar year |
| VEEV | 1393052 | Veeva Systems | middle | Industry specific software |
| BOX | 1372612 | Box | middle | Smaller company |
| TWLO | 1447669 | Twilio | middle | Acquired Segment (2020) |
| OKTA | 1660134 | Okta | middle | Acquired Auth0 (2021) |
| MDB | 1441816 | MongoDB | middle | Typical SaaS |
| DOCU | 1261333 | DocuSign | middle | Typical SaaS |
| ZM | 1585521 | Zoom Communications | middle | Renamed 2024 |
| CRWD | 1535527 | CrowdStrike | middle | Typical SaaS |
| DDOG | 1561550 | Datadog | middle | Calendar year |
| ZS | 1713683 | Zscaler | middle | July year end |
| SNOW | 1640147 | Snowflake | new | Public 2020 |
| PATH | 1734722 | UiPath | new | Public 2021 |
| GTLB | 1653482 | GitLab | new | Public 2021 |
| IOT | 1642896 | Samsara | new | Public 2021; 52/53 week year |
| KVYO | 1835830 | Klaviyo | new | Public 2023 |
| RBRK | 1943896 | Rubrik | new | Public 2024 |
| FIG | 1579878 | Figma | new | Public 2025; one annual report so far |
| SPLK | 1353283 | Splunk | gone | Acquired by Cisco 2024; last 10-K 2023 |
| ZEN | 1463172 | Zendesk | gone | Taken private 2022; last 10-K 2022 |
| TEAM | 1650372 | Atlassian | rule_changer | IFRS 20-F through 2022, US GAAP 10-K from 2023 |
| ESTC | 1707753 | Elastic | rule_changer | Dutch company filing 10-K; April year end |

Date range: `start_year: 2009`, no end year.

## 6. Phase 0: Foundation

Repository layout:

```
config/
  companies.yml
src/xbrl_reconcile/
  config.py            load and validate config, apply defaults
  ingest/
    http.py            polite HTTP client (User-Agent, rate limit, retries)
    sec.py             SEC specific calls and change detection
    storage.py         write raw files to B2 or a local folder
    run.py             entry point: loop companies, land raw, update state
tests/
infra/terraform/
.github/workflows/
  ci.yml               lint and tests on push
  ingest.yml           daily ingestion
docs/
  design.md
pyproject.toml
```

Tooling:

| Need | Choice | Reason |
|---|---|---|
| Python env and deps | uv | Fast, single tool for venv, deps and lockfile |
| HTTP | urllib (stdlib) | Only simple GETs; avoids an extra dependency |
| Object storage client | boto3 | Standard S3 client; works with B2, AWS, LocalStack |
| Config parsing | PyYAML | Already a dbt dependency |
| Lint | ruff | Single fast linter and formatter |
| Tests | pytest | Standard |

Local data (`data/`) and Terraform files with secrets are gitignored.

## 7. Phase 1: Ingestion

### 7.1 Config (`config/companies.yml`)

```yaml
defaults:
  start_year: 2009
  end_year: null
  enabled: true
  report_types: [10-K, 10-K/A, 10-Q, 10-Q/A, 20-F, 20-F/A]

companies:
  - cik: 1108524
    ticker: CRM
    name: Salesforce
    description: Sales and customer management software
    group: old_timer
    events:
      - { year: 2019, note: Acquired Tableau }
      - { year: 2021, note: Acquired Slack }
    notes: Renamed from salesforce.com in 2022
```

Rules:

- Any key in `defaults` may be overridden per company. Company value wins.
- Unknown keys raise an error (catches typos).
- `cik` is the unique key. `ticker` is a label only.
- `group`, `description`, `events`, `notes` are descriptive; `events` is
  later used as context when a company's tag usage changes.
- Facts SEC already provides (fiscal year end, former names, industry code)
  are read from submissions data, never duplicated in config.
- `start_year` and `end_year` are applied when modeling (Phase 2), not at
  download, because companyfacts is one file holding all years.
- A check command verifies every CIK against SEC records.

### 7.2 Run flow

```
for each enabled company:
    fetch submissions
    newest = latest filing whose form is in report_types
    if newest accession == last_seen[cik]:  skip
    else:
        fetch companyfacts
        write submissions and companyfacts snapshots (gzip, unmodified,
        named by run timestamp)
        last_seen[cik] = newest accession
write _state/last_seen.json
report failures; exit non zero if any company failed
```

On the first run there is no state, so every company is downloaded.

### 7.3 SEC etiquette and errors

- User-Agent includes a contact email, read from the `SEC_CONTACT_EMAIL`
  environment variable.
- At most 10 requests per second (SEC limit); client paces below that.
- Retry on HTTP 429 and 5xx with increasing waits, limited attempts.
- One company failing does not stop the others.

### 7.4 Raw layout in the bucket

```
raw/sec/submissions/cik=0001108524/2026-09-16T061502Z.json.gz
raw/sec/companyfacts/cik=0001108524/2026-09-16T061502Z.json.gz
raw/sec/_state/last_seen.json
```

- Folder per CIK (zero padded to 10 digits, matching SEC URLs).
- File names are the UTC run timestamp in ISO 8601 basic time format
  (`YYYY-MM-DDTHHMMSSZ`, no colons). Multiple runs on the same day never
  overwrite each other, and names sort chronologically.
- Submissions and companyfacts written in the same run share one timestamp.
- Snapshots are never moved or modified. The newest timestamp is the
  current version; older ones are history.
- A snapshot is written only when a new report is detected.
- Estimated growth: about 50 MB per year for 28 companies. Free tier is 10 GB.
  A lifecycle rule to expire old snapshots can be added later if needed.

### 7.5 Storage modes

`STORAGE_BACKEND=b2` writes to Backblaze. `STORAGE_BACKEND=local` writes the
same layout under `data/raw/` for offline development and tests.

### 7.6 Schedule (`.github/workflows/ingest.yml`)

- Daily cron at 06:00 UTC, plus manual trigger.
- A concurrency group allows only one ingestion run at a time; a new run
  waits for the current one to finish.
- Reads credentials from GitHub Actions secrets and variables.
- Note: GitHub disables scheduled workflows in public repositories after 60
  days without repository activity. To be handled when it matters.

### 7.7 Infrastructure (Terraform, `infra/terraform/`)

Managed resources:

| Resource | Provider |
|---|---|
| Private B2 bucket for raw data | Backblaze/b2 |
| Application key scoped to that bucket only | Backblaze/b2 |
| Actions secrets: `B2_KEY_ID`, `B2_APPLICATION_KEY`, `SEC_CONTACT_EMAIL` | integrations/github |
| Actions variables: `B2_BUCKET`, `B2_ENDPOINT` | integrations/github |

Decisions:

- The workflow YAML lives in git as normal code; Terraform manages what the
  workflow needs, not the workflow file.
- State stored in HCP Terraform free tier (limit 500 resources; this uses
  about 10), local execution mode so Terraform runs from the developer laptop.
- Terraform's own credentials (B2 master key, GitHub fine grained token) come
  from local environment variables and are never committed.
- Terraform is run manually when infra changes, not by the daily job.
- Manual one time step: set a $0 spending cap in the Backblaze account.

### 7.8 Testing

- Unit tests use recorded sample SEC responses and local storage mode; no
  network calls in tests.
- Covered: config defaults and overrides, unknown key rejection, change
  detection by report type, timestamped snapshot paths (two runs on one day
  produce two files), per company failure isolation.

## 8. Open decisions for later phases

Phase 2 (staging)
- Keep first reported and latest restated values side by side; choose in marts.
- Derive Q4 as full year minus nine month year to date where needed.
- Separate instant facts (balance sheet) from duration facts (income, cash flow).
- Where the dbt DuckDB file lives (built in CI from raw and stored in B2 is
  the leading option).

Phase 3 (mapping)
- Initial canonical concept list (about 15).
- Tag mapping file format (YAML with generated dbt seed, or CSV seed directly).
- Priority when a company reports several candidate tags for the same period.

Phase 4 (custom tags)
- Which quarters of Financial Statement Data Sets to pull and how to filter.

Phase 5 (marts)
- Fiscal year versus calendar year alignment for cross company comparison.

Phase 6 (linkbase)
- Which filings to parse (for example latest 10-K per company).

Phase 7 (API)
- Hosting: local only, or a student credit host. Not a dependency of the pipeline.
