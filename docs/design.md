# xbrl-reconcile: Design

Status: Phases 0 to 4 built. Later phases list open decisions only.
Last updated: 2026-09-26

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
| 0 | Foundation | Done. Repo layout, Python env, config, lint and tests in CI |
| 1 | Ingestion | Done. companyfacts and submissions landed raw in Backblaze B2 daily; infra in Terraform |
| 2 | dbt staging | Done. One row per fact, incremental, tested, published to B2 |
| 3 | Mapping and intermediate | Done. 16 canonical concepts, confidence on every value, coverage report |
| 4 | Data Sets | Done. Dimensional facts and custom tags from SEC's quarterly Data Sets |
| 5 | Marts and tests | Done. Income statement, balance sheet, cash flow, confidence report, published as Parquet |
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
    notes: Deliberate merger case for tag drift
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
| Actions secrets: `B2_INGEST_KEY_ID`, `B2_INGEST_KEY`, `SEC_CONTACT_EMAIL` | integrations/github |
| Actions variables: `B2_BUCKET`, `B2_ENDPOINT` | integrations/github |

Decisions:

- The workflow YAML lives in git as normal code; Terraform manages what the
  workflow needs, not the workflow file.
- State stored in HCP Terraform free tier (limit 500 resources; this uses
  about 10), local execution mode so Terraform runs from the developer laptop.
- The workflow key is named `B2_INGEST_KEY_ID` and `B2_INGEST_KEY` so it is
  never confused with the Backblaze provider's own `B2_APPLICATION_KEY_ID`
  and `B2_APPLICATION_KEY` environment variables used by Terraform.
- Terraform's own credentials (B2 master key, GitHub fine grained token) come
  from local environment variables and are never committed.
- Terraform is run manually when infra changes, not by the daily job.
- No payment method is kept on the Backblaze account, so charges are
  impossible: past the free tier, uploads fail instead of billing. Editing
  spending caps requires a card on file and is therefore skipped.
- Backblaze free tier also allows 1 GB of downloads per day, which matters
  when dbt reads the raw layer in Phase 2 (about 150 MB total today).

### 7.8 Testing

- Unit tests use recorded sample SEC responses and local storage mode; no
  network calls in tests.
- Covered: config defaults and overrides, unknown key rejection, change
  detection by report type, timestamped snapshot paths (two runs on one day
  produce two files), per company failure isolation.

## 8. Phase 2 and 3 groundwork (decided while exploring the data)

### 8.1 What the raw data actually is

Verified against Salesforce's companyfacts file (31,386 facts, 704 concepts).

- The file is not a filing. It is every fact from every filing the company has
  made, accumulated. Each fact carries `accn`, the filing that reported it.
- Every snapshot is a full copy; a new 10-Q adds roughly 300 to 450 facts to a
  file of 31,000.
- A fact's business key is `taxonomy + concept + unit + period_start +
  period_end`. Verified: that key plus `accession` is unique across the file,
  and the key alone is reported by up to 11 filings.
- 49 percent of business keys are reported more than once. 779 of 17,181 have
  more than one distinct value, which are restatements. Example: total assets
  at 2018-01-31 reported as 21,009,802,000 then restated to 21,984,000,000.
- Facts are either duration (income statement, cash flow; has `start`) or
  instant (balance sheet; no `start`).
- No quarter ever ends on the fiscal year end, so Q4 must be derived as full
  year minus nine months.
- `fy` and `fp` describe the filing, not the period, and are not used.
- companyfacts carries consolidated facts only; dimensional breakdowns such as
  segment revenue are excluded by SEC, so the key needs no dimension part.

### 8.2 Taxonomies present

| Taxonomy | Contents | Used for mapping |
|---|---|---|
| us-gaap | Financial statements under US rules | Yes |
| ifrs-full | Financial statements under international rules (Atlassian) | Yes, flagged as a different basis |
| dei | Cover page facts such as shares outstanding and public float | Kept, used later for per share figures |
| ecd | Executive compensation, filed in DEF 14A | Kept, not mapped |
| ffd | Filing fee disclosures, filed in S-8 and similar | Kept, not mapped |
| srt, invest | Shared building blocks and a retired investment taxonomy | Kept, not mapped |

Staging keeps every taxonomy. Mapping reads us-gaap and ifrs-full only.

### 8.3 Scale of the mapping problem

Across the 28 companies: 2,047 distinct us-gaap concepts, of which 42 are used
by all 28 and 774 by exactly one company. Per company the range is 230 to 691.

Revenue alone is reported under at least five standard tags. CrowdStrike uses
RevenueFromContractWithCustomerIncludingAssessedTax while most peers use the
Excluding variant. Salesforce reports two candidate tags for fiscal 2018 with
values 60 million apart, the original and the ASC 606 restatement.

### 8.4 Tag mapping config shape

`config/tag_mappings.yml`, source of truth in YAML, converted to a dbt seed by
a small command.

```yaml
concepts:
  revenue:
    statement: income_statement
    tags:                    # list order is the priority, first match wins
      - { tag: "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", confidence: high }
      - { tag: "us-gaap:Revenues", confidence: high }

company_overrides:
  - cik: 1650372
    concept: revenue
    prefer: ["ifrs-full:Revenue"]
    through_year: 2022
    note: "Filed 20-F under IFRS until 2022"
  - cik: 1108524
    concept: revenue
    ignore: ["us-gaap:SalesRevenueServicesNet"]
```

Rules:

- Order in `tags` is the priority. Position becomes a priority number when the
  seed is generated, so no numbers are typed by hand.
- `prefer` puts tags ahead of the global order for one company.
- `ignore` removes a tag from consideration for that company entirely, which is
  different from ranking it last.
- `through_year` and `from_year` bound an override to a period range.
- Resolution order: company override for the year, then company override, then
  global order.

### 8.5 Onboarding a new company

1. Add the company to `config/companies.yml`.
2. Run the pipeline.
3. Read the mapping coverage report, which lists unmapped and ambiguous
   company and period combinations.
4. Add tag mappings or overrides only for what it flags.

No code changes. The five global revenue tags already cover all 28 companies
with no overrides.

### 8.6 Decisions on disagreement, keys and reporting basis

**Restated values: keep both.** The mart column `value` carries the latest
filed value. Alongside it, `originally_reported_value`, `restatement_count`
and `was_restated` make the rewrite visible. Evidence: Intuit has 1,065
business keys reported with more than one value, and 932 of those differ by
more than one percent, so the choice is material rather than cosmetic. A fact
restated several times is also a confidence signal for the mart's companion
report.

**Form type is an attribute, not part of the key.** The business key stays
`taxonomy + concept + unit + period_start + period_end`. `form` travels as a
column so models can still prefer 10-K values when that is wanted. Putting
form in the key would leave two permanent current values per period, since
disagreements track filing date rather than form: total assets at 2018-01-31
were 21,009,802,000 in the 10-K and 21,984,000,000 in the next 10-Q.

**IFRS years are mapped, with a `basis` column.** Every mart row carries `basis`
as `us_gaap` or `ifrs`, and IFRS values are capped at medium confidence because
the underlying rules differ.

Corrected 2026-09-25: this section originally said the two bases never overlap,
based on revenue alone. They do overlap. Atlassian reports net income under
ifrs-full for periods ending 2016 to 2022 and under us-gaap from 2021, so 2021
and 2022 exist under both, with values 117 million apart in 2021. They never
share a business key, because the taxonomy is part of the key, but they do
describe the same periods. Phase 3 resolves this by preferring us_gaap
deliberately rather than by filing date (section 10.4).

## 9. Phase 2 as built: the staging layer

Built 2026-09-21 to 2026-09-23. Runs daily in GitHub Actions, chained after
ingestion, reading and writing Backblaze. Nothing depends on a laptop.

### 9.1 Shape of the layer

```
raw/sec/companyfacts/cik=<cik10>/<run_ts>.json.gz    cumulative SEC snapshots
raw/sec/submissions/cik=<cik10>/<run_ts>.json.gz     filing lists
raw/config/companies/<run_ts>.json                   the company list, as data
raw/sec/_state/last_seen.json                        accessions plus last_run
        |
        |  dbt (dbt-duckdb), models in transform/models/staging
        v
stg_companies        one row per configured company
stg_sec_facts        one row per fact as reported
stg_ingest_state     one row: when ingestion last ran
        |
        v
warehouse/xbrl.duckdb    fetched before the build, published after it
```

### 9.2 Staging grain

`stg_sec_facts` is one row per fact as a filing reported it, with nothing
deduplicated. A business key repeats once per filing that reported it, which is
how restatements stay visible.

| Column | Source |
|---|---|
| cik, entity_name | top of the companyfacts file |
| ticker | joined from stg_companies |
| taxonomy, concept, concept_label, unit | the JSON nesting |
| period_start, period_end | start and end |
| period_type, period_days | derived: instant when start is null |
| value, accession, form, filed_date, frame | the fact entry |
| is_valid | derived: false when a data quality rule failed |
| source_file | which snapshot the row came from |

Facts are not filtered by `start_year`; that happens downstream.

### 9.3 Decisions

| Decision | Reason |
|---|---|
| Read the newest snapshot per company only | Snapshots are cumulative, so older ones add duplicates and no information. They stay in raw as history |
| Give DuckDB an explicit JSON schema | `cik` is a number in 24 files and a zero padded string in 4 (FIG, IOT, KVYO, RBRK); auto detection fails across the set |
| Incremental, delete+insert keyed on cik | A new snapshot replaces that company's facts wholesale. Files already named in source_file are skipped, so the table itself is the record of what has been processed |
| Fetch the database before building | The runner is wiped between runs; without the fetch every run starts empty and the incremental logic never applies |
| Structural tests error, data quality tests warn | A broken transformation makes all 28 companies suspect; one company's odd file should not block the other 27 |
| Quarantine with is_valid rather than dropping rows | A missing value must stay explainable. Downstream models filter on is_valid |
| store_failures on | Turns "3 rows failed" into the actual rows |
| Company config read from a bucket snapshot | One source of truth (config/companies.yml) with no generated copy in git, and the bucket records which list produced which run |
| Freshness measured on a heartbeat, not on data age | Companies file about four times a year, so a quiet fortnight is normal. `last_run` is written on every ingestion run, including no-op runs |
| Warn at 3 days stale, fail at 14 | Stale data is still correct data; blocking publication would punish the wrong thing |

### 9.4 Tests

23 dbt tests. Structural ones (business key uniqueness, not null on cik,
taxonomy, concept, unit, period_end, is_valid, accepted values on period_type)
stop the build. Data quality ones (not null on ticker, value, accession,
filed_date) warn and quarantine. Two singular tests watch the heartbeat:
`pipeline_is_fresh` warns past `freshness_warn_days`, `pipeline_is_not_abandoned`
fails past `freshness_error_days`; both thresholds are vars.

### 9.5 Measured

| Metric | Value |
|---|---|
| Rows in stg_sec_facts | 408,213 |
| Companies | 28 |
| Distinct concepts | 2,279 |
| Business keys | 226,028 |
| Business keys reported more than once | 113,249 |
| Cold build of stg_sec_facts | 9.2s |
| Incremental run with nothing new | 0.17s |
| Published database | about 10.5 MB |
| Raw read per run | about 4.2 MB |

### 9.6 Traps found while building

- **Mixed `cik` types** across companyfacts files; fixed with an explicit schema
  and a cast.
- **A comma inside an unquoted YAML value** silently became a third field, and
  the config validation caught it.
- **`ref()` inside a conditional** is invisible to dbt while parsing; a
  `-- depends_on:` hint is required.
- **A wiped runner defeats incremental models** unless the database is fetched
  back first. The behaviour looked correct locally and did nothing in CI.
- **`glob()` on an empty result** would have produced an empty table silently;
  the macros raise instead, except on incremental runs where empty is normal.

### 9.7 Local development

`RAW_ROOT` pointed at a folder laid out like the bucket, with the `dev` target,
runs the same models with no credentials. CI leaves `RAW_ROOT` unset and gets
the Backblaze path from `B2_BUCKET`.

## 10. Phase 3 as built: mapping and confidence

Built 2026-09-24 to 2026-09-25. Turns 2,047 inconsistent SEC tags into 16
canonical concepts, one value per company, concept and period, each carrying how
it was obtained.

### 10.1 The canonical concepts

| Concept | Statement | Unit | Notes |
|---|---|---|---|
| revenue | income_statement | USD | |
| cost_of_revenue | income_statement | USD | Total, not a component |
| gross_profit | income_statement | USD | Derived where not reported |
| operating_expenses | income_statement | USD | Excludes cost of revenue |
| operating_income | income_statement | USD | |
| net_income | income_statement | USD | Attributable to the parent |
| eps_diluted | income_statement | USD/shares | |
| shares_diluted | income_statement | shares | |
| total_assets | balance_sheet | USD | |
| total_liabilities | balance_sheet | USD | Derived where not reported |
| temporary_equity | balance_sheet | USD | Redeemable convertible preferred stock, which sits between liabilities and equity |
| total_equity | balance_sheet | USD | Includes noncontrolling interests |
| cash | balance_sheet | USD | Excludes restricted cash |
| operating_cash_flow | cash_flow | USD | |
| investing_cash_flow | cash_flow | USD | |
| financing_cash_flow | cash_flow | USD | |

`operating_expenses` excludes cost of revenue because that is what
us-gaap:OperatingExpenses means. `temporary_equity` exists because without it 72
balance sheets did not balance.

### 10.2 Config mechanisms

`config/tag_mappings.yml` is validated in Python before dbt reads it, because a
misspelled tag matches nothing and produces silence rather than an error. Three
mechanisms, in the order they apply:

| Mechanism | Purpose |
|---|---|
| Ordered `tags` per concept | The global priority list. First match wins. Position becomes a priority number, so no numbers are typed |
| `company_overrides` with `prefer` | Puts a tag ahead of the global list for one company, and may introduce a tag that is not in the list at all. Carries its own confidence, defaulting to low |
| `company_overrides` with `ignore` | Removes a tag from consideration for one company entirely, which is different from ranking it last |
| `components` per concept | A set of tags that sum to the concept, used only when no total tag matched and every part is present. Never high confidence |

Both configs are snapshotted to the bucket by the ingestion run
(`raw/config/tag_mappings/`, `raw/config/tag_mapping_overrides/`,
`raw/config/tag_components/`), so every published value traces to the rules that
produced it. Ingestion validates the mapping config against the company config
before making any SEC request.

### 10.3 The model chain

```
stg_sec_facts, stg_tag_mappings, stg_tag_overrides, stg_tag_components
        |
int_facts_mapped      one row per company, concept, period and filing
        |             tag chosen by priority; component sums as a fallback
int_facts_resolved    one row per company, concept and period
        |             latest filed wins, original kept, restatement counted
int_facts_derived     concepts computed from resolved values
        |
int_facts             the layer's output: reported plus derived
        |
mart_mapping_coverage, mart_unmapped_tags
```

Derivation reads resolved values rather than per filing values, so a derived
number always equals the published inputs it came from. Deriving per filing was
tried first and produced statements that did not add up.

### 10.4 Resolution rules

- Resolution happens per filing first, so a restatement is never decided by
  accident.
- A company override may introduce a tag; global rules apply to every company.
- Units must match the concept's declared unit, so a per share value cannot land
  in a total.
- Balance sheet concepts take instant facts, income and cash flow concepts take
  durations.
- US GAAP is preferred over IFRS deliberately, not by filing date, so a peer
  comparable value wins wherever both exist.
- Restatements are measured within one basis, so a rulebook change is not
  mislabelled as a restatement.
- Derivations are universal accounting identities and live in code:
  `gross_profit = revenue - cost_of_revenue`,
  `operating_expenses = revenue - cost_of_revenue - operating_income`,
  `total_liabilities = total_assets - total_equity`. Which companies need them is
  discovered from the data.

### 10.5 The confidence model

| Level | Meaning |
|---|---|
| high | The standard tag for this total, used consistently across the sector |
| medium | A retired tag, a different reporting basis, a component sum, or a downgrade |
| low | A judgement call for one company, documented in its note |
| derived | Computed from other concepts, never reported by the company |

`high` means "standard tag, used consistently", not "verified against the
filing's own arithmetic". Phase 6 will check mappings against each filing's
calculation linkbase and may upgrade or contradict these.

Two adjustments:

- **Disagreement downgrade.** When more than one candidate tag matched and the
  values differ by more than `candidate_tolerance`, confidence drops one level,
  because the choice was ours. Candidates that agree leave confidence alone: 781
  of 47,254 rows were downgraded.
- **`inputs_confidence`** carries the weakest input confidence for derived rows,
  so a value derived from high confidence inputs is distinguishable from one
  derived from low.

### 10.6 Deliberate exclusions

| Tag | Excluded from | Evidence |
|---|---|---|
| us-gaap:SalesRevenueServicesNet | revenue | Adobe's 2008 10-K reports Revenues 3,579,889,000 and this 183,347,000. A component |
| us-gaap:CostsAndExpenses | operating_expenses | Includes cost of revenue: Intuit's revenue minus this equals operating income exactly |
| us-gaap:LiabilitiesAndStockholdersEquity | total_liabilities | Equals total assets |
| us-gaap:CostOfServices, us-gaap:CostOfGoodsSold | cost_of_revenue as totals | Reported together as parts. Handled by component summation instead |
| us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents | cash | A superset of cash, and the companies concerned report the plain tag as well |

A tag is excluded rather than ranked last, because a tag ranked last still wins
whenever nothing above it matches.

### 10.7 Measured results

| Metric | Value |
|---|---|
| Rows in int_facts | 21,951 |
| Companies, concepts | 28, 16 |
| Coverage of the annual grid | 96.2 percent reported |
| high / medium / derived | 20,877 / 881 / 193 |
| Restated periods | 950 of 21,780, 4.4 percent |
| dbt tests | 125 |
| Python tests | 100 |

Remaining gaps, 62 annual cells:

| Group | Cells | Cause |
|---|---|---|
| Workday cost of revenue and gross profit | 26 | Reported dimensionally; companyfacts drops dimensional facts |
| Intuit 2018 onward | 27 | Same: the missing expense detail is dimensional |
| First year and IFRS transition edges | 9 | Structural |

A further 64 cells are labelled `no_balance_sheet` rather than missing: US rules
require three years of income statements but only two balance sheets, so a
company's earliest fiscal year has no balance sheet at all.

### 10.8 Traps found while building

- **`prefer` could not introduce a tag.** Splunk reports no NetIncomeLoss, and
  its override was inert because the join only considered globally listed tags.
  Now a prefer override adds a company scoped rule.
- **A component mapped as a total.** Intuit's cost of revenue came out as
  677,000,000 (services only) instead of 797,000,000, overstating derived gross
  profit by 120 million. Caught by the derived rows, then fixed by component
  summation.
- **`join ... using (period_start)` dropped every balance sheet fact**, because
  `null = null` is false in SQL and instants have no period start. 4,450 rows
  vanished silently; `is not distinct from` fixes it.
- **Deriving per filing produced statements that did not add up.** Intuit's 2017
  gross profit was computed inside an older filing while revenue came from a
  newer one. Derivation moved after resolution.
- **The balance sheet needs temporary equity.** Without it 72 periods did not
  balance; Klaviyo's 2022 gap closed to exactly zero once added.
- **Total equity must include noncontrolling interests.** GitLab's gap equalled
  MinorityInterest exactly.
- **A verification that failed and stopped a feature.** Deriving Intuit's cost of
  revenue as CostsAndExpenses minus its three named expense tags was tested
  against ten known years and overshot in every one, by up to 55 percent. The
  feature was abandoned rather than shipped at low confidence.
- **The consistency tests were proved by injection.** Pointing Adobe's revenue at
  the services component took failures from 1 to 129, with Adobe 108 percent out.
  A test that has never failed is a hypothesis.

### 10.9 Coverage report and worklist

`mart_mapping_coverage` is a grid of company, concept and fiscal year with a
status of reported, derived, ambiguous, no_balance_sheet or missing. Instants are
matched to the fiscal year whose end date they fall on, because an instant three
months after a January year end belongs to the following year.

`mart_unmapped_tags` lists tags a company reports that match no rule, with how
many peers use each. It found both remaining mapping gaps without anyone reading
a filing: `EarningsPerShareBasicAndDiluted` (14 companies) and
`WeightedAverageNumberOfShareOutstandingBasicAndDiluted` (18 companies), which
loss making companies use because basic and diluted are then equal. Adding two
config lines closed 127 missing cells.

## 11. Phase 4 as built: the Financial Statement Data Sets

Built 2026-09-26. Recovers the facts `companyfacts` throws away: values reported
only as a breakdown by dimension, and company specific custom tags.

### 11.1 Why the phase exists

The design called this phase "custom tags". Measured, the proportions are the
other way round: **one third of all facts in our companies' filings are
dimensional** (131,908 of 395,773 across 69 quarters), and SEC's JSON API drops
every one of them.

Workday never tags total cost of revenue. It reports
`CostOfGoodsAndServicesSold` split as `SubscriptionServices` plus
`ProfessionalServices`, so `companyfacts` shows nothing and 26 coverage cells
were empty. In its fiscal 2017 10-K the same concept was a **custom** tag,
`CostOfRevenueSubscriptionAndSupport`, so both mechanisms are needed: custom tags
for the older years, dimensions for the recent ones.

### 11.2 The source

| Fact | Value |
|---|---|
| URL | `https://www.sec.gov/files/dera/data/financial-statement-data-sets/YYYYqN.zip` |
| Available | 2009q2 to 2026q2, 69 published quarters |
| Zip size | 58 to 85 MB per quarter, 4.2 GB in total |
| Files | `sub.txt` filings, `num.txt` facts, `tag.txt` definitions, `pre.txt` statement lines |
| `num.txt` | 3.6 million rows, 600 MB uncompressed, for one quarter |
| Our share | about 8,800 rows a quarter |
| Stored after filtering | **9.8 MB for seventeen years** |

`num.txt` columns: `adsh, tag, version, ddate, qtrs, uom, segments, coreg, value,
footnote`. `qtrs` encodes duration (0 instant, 1 quarter, 2 half, 3 nine months,
4 annual), `segments` holds dimensions as `Axis=Member;`, and `version` for a
custom tag is the accession number of the filing that declared it.

The header is byte identical in 2009q2, 2017q1 and 2026q2, so the format has held
for seventeen years. Files are still parsed by header name rather than column
position.

### 11.3 Ingestion

```
raw/fsds/<quarter>/{sub,num,pre,tag}.tsv.gz
raw/fsds/<quarter>/_filtered_for.json      which CIKs the quarter was filtered for
raw/fsds/_state/quarters.json              the index of landed quarters
```

Decisions:

- **Filter before storing.** 70 quarters of raw zips would be 4.2 GB of a 10 GB
  free tier, 99.7 percent of it other companies. Filtering is by company only and
  the surviving rows are the bytes SEC published, so the raw layer stays faithful.
- **Byte level matching, never decoding.** Company names in `sub.txt` contain
  bytes that are not valid UTF-8; a decode and re-encode round trip would alter
  them.
- **Four passes in order**, because only `sub.txt` maps a filing to a company:
  read `sub`, then filter `num` and `pre` by the filings found, then filter `tag`
  to the definitions those facts used.
- **The quarter is the version.** SEC never revises a published quarter, so
  files are not timestamped and a landed quarter is never re-fetched.
- **Quarter selection comes from the company config.** A quarter is needed by a
  company when it is enabled and the quarter's year falls between its
  `start_year` and its `end_year` plus one. The plus one is because a final
  fiscal year is reported in a filing submitted the following calendar year.
- **Each quarter records the CIKs it was filtered for**, and a quarter is fetched
  when the CIKs it should cover are not already a subset of what it recorded. So
  adding a company re-fetches only the quarters its own range covers, removing one
  re-fetches nothing, and there is no second setting to disagree with the first.
- **A 404 means not published yet**, not a failure: a quarter appears about six
  weeks after it ends. Candidates are floored at 2009q2, SEC's first set, so a
  quarter that will never exist is never requested.
- **Batches.** A backfill runs in chunks (default 8 quarters, workflow input to
  override) rather than one long job. The full 69 quarter backfill took 8 minutes.

### 11.4 Recovering a total by summing one dimension

`int_fsds_dimension_totals` sums the members of one axis where a company reports
no total. Six safeguards, because summing parts is where double counting hides:

1. Only axes listed in config (`summable_axes`), because whether an axis
   partitions a total is a judgement about the axis. `ProductOrService` is the
   only entry.
2. Only facts with exactly one dimension. A fact split by product and by
   geography at once would be counted twice.
3. At least two members; one member is not a breakdown.
4. No consolidated row for the same tag, period and unit in any filing.
5. **Nothing already reported for the concept that tag maps to, under any tag.**
   Autodesk taught this: it reports `CostOfRevenue` as a consolidated total (650
   million for fiscal 2026) and `CostOfGoodsAndServicesSold` as a two member
   breakdown summing to 553 million, which is part of cost of revenue rather than
   all of it. Guarding at tag level alone published a total 15 percent short.
6. Within one filing, one period end, one period kind and one unit.

Recovered totals enter `int_facts_mapped` as a third candidate source at priority
2000, behind every reported total and every component sum, with `source_tag`
recorded as `fsds:<taxonomy>:<Tag>@<Axis>` and confidence capped at medium.

**Period alignment.** The Data Sets give a period end and a length but no start
date, while the business key uses `period_start`. A recovered value takes the
start date the company already uses for that period end and length, falling back
to arithmetic only for a period no other concept covers. Every recovered row in
the current data matched, which is what lets a recovered value line up with the
rest of its statement.

**The check that matters.** Workday's recovered cost of revenue gives a gross
margin of 75.7, 75.5 and 75.6 percent for fiscal 2026, 2025 and 2024. A wrong
total would wander; a stable mid seventies margin is what Workday reports.

### 11.5 Optional concepts

Coverage counted 230 cells as missing that were `temporary_equity` for companies
with no redeemable preferred stock. Absence there is an answer, not a gap, and
nothing in the facts distinguishes "has none" from "not mapped". So a concept can
declare `optional: true` and its absence becomes the status `not_applicable`.
Only `temporary_equity` carries the flag, and a test enforces that.

### 11.6 Results

| Metric | Value |
|---|---|
| Quarters landed | 69 |
| Filings | 1,029 |
| Facts | 395,773 |
| Dimensional facts | 131,908, one third of the total |
| Custom tag facts | 21,876 across 192 distinct tags |
| Coverage: reported | 4,645 cells |
| Coverage: derived | 67 |
| Coverage: **missing** | **18**, from 56 before the phase |
| dbt tests | 174 |
| Python tests | 132 |

Gaps closed: Intuit's operating expenses from 9 missing years to 1, Workday's
cost of revenue from 13 to a handful, gross profit from 19 cells to 4. The
remaining 18 are single year edges.

`mart_custom_tags` surfaces what companies invented, with how many peers invented
the same name. Six companies independently created a tag for the same capitalized
contract cost movement, and two of them differ only by a plural, which is the
project's premise in one row. None of them is one of the 16 concepts, so nothing
is mapped from them yet.

### 11.7 Traps found while building

- **A guard at the wrong level.** Autodesk's case above: the fix was to guard at
  concept level rather than tag level.
- **A company blind file list.** `stg_sec_facts` globbed `cik=*` rather than
  reading the config, so a removed company's snapshots were still read and
  quarantined, warning on every run forever. Staging now reads configured
  companies only.
- **`enabled: false` did nothing downstream.** Phase 2 claimed models filtered on
  it; none did. `int_facts_mapped` now joins enabled companies only, while staging
  keeps disabled ones so re-enabling needs no download.
- **A candidate list that chased a quarter that never existed.** 2009q1 is before
  SEC's first set, so it 404ed on every run and was reported as not published yet.
- **Adding a config snapshot type is order dependent.** The first production
  transform after this phase failed, because `stg_tag_summable_axes` read a
  snapshot that ingestion had not yet written. Ingestion writes config snapshots,
  so a new snapshot type needs an ingest run before the next transform. Normal
  operation chains them correctly; only a manual transform first breaks.

## 12. Phase 5 as built: the marts

Phase 5 turns reconciled facts into statements a person can read: an income
statement, a balance sheet and a cash flow statement per company and period, each
line carrying how the number was obtained, published as Parquet so a reader needs
kilobytes rather than a warehouse.

### 12.1 The model chain

```
int_facts (Phase 3)
  -> int_facts_quarterly      the fourth quarter, which no filing covers
  -> int_periods              every period labelled with a fiscal and a calendar year
  -> int_statement_filings    which single filing a whole statement can be read from
  -> mart_financials          one row per company, concept and period
       -> mart_income_statement | mart_balance_sheet | mart_cash_flow
       -> mart_confidence_report
```

`int_periods` reads both `int_facts` and `int_facts_quarterly`, because a derived
quarter is a period no filing covers and would otherwise carry no label. The
quarterly model does not read the spine, which is what keeps that from being a
cycle, and is why it matches periods on dates rather than on year labels.

### 12.2 A fiscal year is not a calendar year

Sixteen of the 28 companies end their financial year in January, nine in December,
and the rest in February, April, June, July or November. One label year therefore
spans **335 days**: fiscal 2025 ends anywhere from 2025-01-31 to 2025-12-31.
Comparing companies on that label compares different years.

Two companies also changed their year end outright, and two do not have a fixed
one at all:

| Company | Fiscal calendar |
|---|---|
| ServiceNow | June year end through 2011, then December, with a six month stub |
| Workday | December year end through 2010, then January, with a one month stub |
| Adobe | 52/53 weeks, ending 11-27 to 12-03; fiscal 2021 ran 370 days |
| Samsara | 52/53 weeks, ending 01-28 to 02-03; fiscal 2024 ran 370 days |

So a period's fiscal year cannot be computed from its end date, and cannot come
from one anchor per company either. `int_periods` takes it from the company's own
annual periods: a period belongs to the fiscal year closed by the next annual
period end the company reported, with a 15 day tolerance that absorbs the 52/53
week drift. Where a period runs past the newest annual report, or more than a year
before the nearest one, that year end is stepped whole years to reach it, which
keeps the company's own month and day instead of assuming a calendar year.

**Two year labels are published, because they answer different questions.**
`fiscal_year` is what the company calls the year, which is what a reader checking
a number against the filing needs. `calendar_year_equivalent` is the calendar year
holding most of that fiscal year's days, computed as the year 183 days before the
year end. Salesforce fiscal 2026 and ServiceNow fiscal 2025 cover almost the same
twelve months of real time, and only the second label says so.

Nothing relabels a period onto calendar quarters. Commercial data providers do,
and it makes comparison easy, but it publishes a figure under a period the company
never reported, which this project treats as a fabrication rather than a
convenience.

`year_end_is_observed` is false where the year end was inferred rather than filed:
**139 of 3,093 periods**, almost all in a fiscal year whose annual report has not
been filed yet, plus Splunk's final stub year and the two calendar changes.

### 12.3 The fourth quarter

A company files three 10-Qs covering three, six and nine months, then a 10-K
covering the year. No report covers the final three months alone, so Q4 is a hole
by construction. `int_facts_quarterly` closes it with the full year minus the nine
month figure, which works because both are cumulative from the same fiscal year
start. That is also why the two are matched on an identical `period_start` rather
than on a year label: during a fiscal calendar change a year label would pair the
wrong two periods.

Three rules keep it honest.

1. **Additive concepts only.** Earnings per share is a ratio and a diluted share
   count is a weighted average, so subtracting one period from another produces a
   number that means nothing. Which concepts those are is declared in config as
   `additive: false`, because nothing in the facts distinguishes a ratio from a
   sum. Without this the model would have produced 558 confidently wrong values.
2. **A reported quarter is never shadowed.** 399 Q4 facts across 78 company years
   already exist, mostly through the Data Sets, so a derived row is produced only
   where no quarter exists for that period end.
3. **Balance sheets are untouched.** They are instants, and the fourth quarter
   balance sheet is the year end one, already reported.

Of 3,460 annual concept years, 3,071 have a nine month counterpart, 2,504 of those
are on additive concepts, and 305 already had a reported quarter, leaving
**2,199 derived fourth quarters**. Each carries `confidence = 'derived'` and
`source_tag = 'derived:annual-nine_month'`.

Filling missing first, second and third quarters by the same subtraction of
cumulative periods was considered and deferred: those gaps are a tagging choice
rather than a structural one, and chaining subtractions needs two figures from two
filings to agree.

### 12.4 Statement coherence: publish both, and label them

Every value is resolved on its own, taking the latest figure filed for it. That is
the right answer to "what is this number" and the wrong one to "show me a balance
sheet", because a company can restate one line of an old statement and never
re-report the rest.

Salesforce's balance sheet at 2017-01-31, in millions:

| Filing | Filed | Assets | Liabilities | Equity |
|---|---|---|---|---|
| 10-K | 2017-03-06 | 17,584.9 | 10,084.8 | 7,500.1 |
| 10-K | 2018-03-09 | 17,584.9 | 10,084.8 | 7,500.1 |
| 10-Q | 2018-11-28 | | | **8,230.0** |
| 10-K | 2020-03-05 | | | 8,230.0 |

Everything up to March 2018 balances exactly. ASC 606 then revised equity alone,
and assets were never re-tagged for that date. Taking the latest of each leaves the
balance sheet 729.9 million out. **The restated 2017 balance sheet does not exist
in XBRL as a whole**, which rules out any answer claiming to publish the correct
one.

How widespread, by statement:

| Statement | Draws on one filing | Two | Three or more | Mixes filings |
|---|---|---|---|---|
| cash_flow | 1,320 | 0 | 0 | 0% |
| income_statement | 1,435 | 413 | 15 | 23% |
| balance_sheet | 149 | 732 | 280 | 87% |

Mixing is usually harmless, because only 1.8% of balance sheet values and 5.1% of
income statement values were ever revised. It breaks a statement only when a
restatement touched one line and not the others.

Of the 26 balance sheets that failed the identity before this phase, **22 balance
exactly inside a single filing**. Three were a missing tag in config, and one is
absent from the source data:

- `us-gaap:TemporaryEquityCarryingAmount`, the single tag used before SEC split it
  in 2013, was not mapped. Adding it fixed three Salesforce balance sheets whose
  gaps were exactly the redeemable preferred stock they reported.
- Workday at 2012-01-31 is 73% out. Its pre-IPO redeemable preferred stock of
  170.9 million was never tagged for that date, so it is a coverage gap.

**The decision: publish both.** `value` stays the latest filed figure.
`int_statement_filings` chooses, per company, statement and period, the filing
covering the most of the statement's published lines and, among equals, the most
recently filed. Coverage comes first deliberately: recency first would select the
2020 10-K that reports Salesforce's 2017 equity alone and call one line a balance
sheet. `value_as_filed` is that filing's figure, and `is_coherent` records whether
the two agree.

Publishing only the latest would leave 22 statements visibly broken with no
explanation available in the data. Publishing only the coherent filing would print
7,500.1 and silently discard a correction the company made. A single filing carries
the whole statement in 100% of cash flow statements, 99.5% of balance sheets and
97.3% of income statements, so the choice is nearly always available.

Derived values have no filed counterpart and are excluded from the check rather
than recomputed inside the chosen filing.

### 12.5 Only the forms config counts as reports

Comparing as-filed against published exposed a bug that had been in every
published value since Phase 3. Elastic's net income, before and after:

| Fiscal year end | Published | Source | Actual |
|---|---|---|---|
| 2021-04-30 | −0.204M | DEF 14A | −129.4M |
| 2023-04-30 | +0.062M | DEF 14A | −236.2M |
| 2025-04-30 | +0.368M | DEF 14A | −108.1M |

A DEF 14A is a proxy statement. Since 2022 it must carry a Pay versus Performance
table, which is tagged in XBRL and includes `us-gaap:NetIncomeLoss`. Filers
routinely tag it in millions, and sometimes against the wrong period context. A
proxy is filed after the 10-K, so under a latest filed rule it won. **100 published
net income values across 21 companies came from proxies**, 23 disagreeing with the
report and 6 by a factor of about 1000, plus 49 values from 8-K earnings releases.

`config/companies.yml` already forbade this: `report_types` lists 10-K, 10-Q, 20-F
and their amendments. But it was only consulted during ingestion, to decide whether
a new report had appeared, while `companyfacts` returns facts from every form a
company ever filed. The declared policy stopped at the ingestion boundary.

The fix carries `report_types` into the company snapshot and filters on it in
`int_facts_mapped` and in both fact sources of `int_fsds_dimension_totals`, since
the Data Sets carry S-1, S-4 and 8-K submissions too. **No value was lost**:
published counts per statement are identical before and after, because every proxy
fact duplicated a figure a report had already filed.

### 12.6 The marts

**`mart_financials`** is the source of truth: one row per company, concept and
period, with three numbers that answer three questions. For Salesforce's equity at
2017-01-31 they are `value` 8,230.0, `originally_reported_value` 7,500.1 and
`value_as_filed` 7,500.1.

Its grain drops `period_start` from the key `int_facts` uses. Adobe reports the
same period twice with start dates one day apart, so at this grain those would be
two rows for one quarter and anything summing quarters would double count. **23
rows** are affected, all Adobe, all 2009 and 2010. The version more filings agree
on wins, which picks the company's settled convention rather than a context typo:
Adobe's fiscal 2009 Q1 ended 2009-02-27, so Q2 starts 2009-02-28, and that is the
start two filings carry against one. One of the 23 is not a pure duplicate, a half
year share count of 531,338,000 against 528,233,000, where the later filing wins.

**The three statement views are generated from config.** A column per line cannot
be written in SQL without naming the concepts, so a macro asks the database what
the config says and writes the columns itself. The order comes from the order the
concepts appear in `config/tag_mappings.yml`, which is already a statement order,
and is the same convention that file uses for `tags`, where order means priority.
Adding a concept adds a column; reordering the file reorders the statement, which
was verified by moving a line and rebuilding.

Each line becomes two columns, the value and its confidence, so a number and how
certain it is are read in one glance. `value_as_filed` is deliberately not a third
column per line: that would take the income statement from 16 concept columns to
24 for a case affecting 119 rows. The statement instead carries `incoherent_lines`
and the filing it was read from.

The grain is the period, not the fiscal year, which dissolves the ServiceNow
problem: its two fiscal years labelled 2011 are two rows, each with its own
`fiscal_year_end`, and nothing has to be hidden.

**`mart_confidence_report`** answers how much to trust a statement rather than what
it says, at the same grain so it joins one to one. It counts lines by confidence,
how many are derived, ambiguous, restated or incoherent, whether the statement is
complete, and whether its identity closes. Completeness is measured against the
lines that always apply, excluding optional concepts, or 945 sound balance sheets
would be called incomplete for lacking redeemable preferred stock.

One word summarises it, and the ordering is a judgement recorded in the model:

| `trust` | Means |
|---|---|
| check | An identity fails, or two candidate tags disagreed |
| mapped | Contains a weaker tag: retired, another rulebook, or recovered from dimensions |
| computed | Contains a value derived from an identity or from adjacent periods |
| reported | Every line is a standard tag the company filed |

A possible error outranks a known approximation, and a weaker tag ranks below a
derived value because a derived value is arithmetic over reported figures while a
weaker tag is a judgement about what a tag means. Incoherence does not affect the
label, because the numbers are not in doubt there, only their provenance.

The identities in this model duplicate those in the consistency tests on purpose:
the tests check them on the figures one filing published together, and the report
checks them on the latest figure for each line. Same arithmetic, different inputs,
different questions. The formulas stay in SQL rather than config for the reason
`int_facts_derived` already records: they are universal accounting identities, not
judgements about companies.

### 12.7 Publishing the marts

The database is 57.4 MB, most of it staging tables nobody querying a statement
needs. The same marts as Parquet are **1.15 MB in total**, and each file stands
alone, so reading the income statement costs 101 KB.

`xbrl-publish-marts` exports every table in the main schema named `mart_`, so
adding a mart publishes it with no code change, compresses with zstd, and uploads
through the same `Storage` object the rest of the pipeline uses. DuckDB can write
straight to the bucket and the dbt profile already holds credentials for reading
it, but going through `Storage` keeps one way of talking to the bucket and lets the
whole export be tested with a temporary database and no credentials.

Files land at `warehouse/parquet/<model>.parquet` and are overwritten each run,
covered by the existing lifecycle rule that deletes superseded versions after seven
days. Overwriting is a write, not a delete, so the scoped key still cannot delete
anything. A `_index.json` written last records each file's row count and when the
run published it, so a reader can see what exists and how fresh it is with a one
kilobyte fetch.

### 12.8 Measured results

Production run 36357622533, 2026-09-27: **293 dbt nodes, 290 pass, 3 warn, 0
errors**, in 1m18s.

| Mart | Rows | Parquet |
|---|---|---|
| mart_financials | 25,326 | 702 KB |
| mart_unmapped_tags | 11,033 | 91 KB |
| mart_mapping_coverage | 5,056 | 40 KB |
| mart_confidence_report | 4,900 | 69 KB |
| mart_income_statement | 2,068 | 101 KB |
| mart_cash_flow | 1,602 | 50 KB |
| mart_balance_sheet | 1,230 | 46 KB |
| mart_custom_tags | 1,092 | 53 KB |

Shares below are from the dev build of the same commit, which has up to four fewer
statements per view.

| Statement | reported | computed | mapped | check |
|---|---|---|---|---|
| balance_sheet | 90.2% | 5.8% | 1.3% | 2.7% |
| cash_flow | 75.1% | 17.6% | 7.3% | 0% |
| income_statement | **50.4%** | 12.4% | 31.6% | 5.5% |

Half the income statements contain at least one line that is not a standard tag the
company filed. That is the project's thesis stated as a number, and before this
phase it took a manual audit to see.

Coverage improved on its own: the pre-2013 temporary equity tag closed two gaps,
leaving **16 actionable missing cells** out of 5,056.

Three standing warnings, all explained rather than outstanding:

- Atlassian fiscal 2017 under IFRS: revenue less cost of sales missed gross profit
  by 6.7 million. This was attributed to IFRS classifying some costs elsewhere, and
  that was wrong. Atlassian restated 2017 and 2018 under IFRS 15 in its 2019 20-F,
  moving revenue from 619.936 to 626.684 and gross profit from 500.775 to 507.523.
  Both vintages are internally consistent. The restated revenue carried a tag,
  ifrs-full:RevenueFromContractsWithCustomers, that nothing mapped, so gross profit
  followed the restatement while revenue could not, and the gap was the two vintages
  mixed. Mapping the tag closed it, and the warning is gone. See section 13.
- Workday at 2012-01-31: the untagged pre-IPO preferred stock.
- Intuit, four company years: its own quarterly figures sum to between 20 and 59
  million away from its annual figure, on restatement free years. A disagreement
  inside the filer's data, not ours.

The quarters to year test restricts to sets where nothing was restated, because
otherwise it reports filing behaviour rather than arithmetic. Salesforce's fiscal
2017 operating income is the clearest case: four unrestated quarters sum to 64.2
million, which is exactly the annual figure as originally reported, while the
annual value is the restated 218.0 million. Without the restriction 71 of 1,763
four quarter sets disagree; with it, 4.

### 12.9 Traps found while building

- **A shadowed loop variable.** `_parse_concept` already used `position` for tag
  priority, so a new `position` parameter was silently overwritten and revenue came
  out as line 5. Two of the three new tests exist because of it.
- **Every `ref()` inside a loop or conditional needs a `depends_on` hint**,
  including in singular tests. The round trip test needed four, and dbt reports
  them one at a time.
- **Date arithmetic widens to a timestamp in DuckDB.** `date - interval` returns a
  timestamp, so the fiscal year end had to be cast back to a date.
- **A measurement taken on a subset does not generalise.** The quarters to year
  check was first measured on revenue since fiscal 2024, worst case 1,000 dollars
  on 3.13 billion. Across all concepts and years the worst case is 70%.
- **A column description that overstates.** `incoherent_lines` above zero was
  documented as meaning the statement will not add up. Salesforce at 2015-01-31 has
  two incoherent lines and balances exactly, because the restatement moved assets
  and equity together.
- **Adding a snapshot field is order dependent**, three times in this phase.
  Ingestion writes the config snapshots, so a new field needs an ingest run before
  the next transform. This is a property of keeping config in the bucket, not an
  accident: the same coupling appeared in Phase 4 and will appear again.

## 13. Open decisions for later phases

Phase 3 (mapping)
- Initial canonical concept list (about 15).
- Tag mapping file format (YAML with generated dbt seed, or CSV seed directly).
- Priority when a company reports several candidate tags for the same period.

Phase 4 (Data Sets): built, see section 11.

Phase 5 (marts): built, see section 12. Statement coherence was settled by
publishing both views; fiscal and calendar year alignment by publishing both
labels; Q4 by subtraction on additive concepts only.

Left open by Phase 5, in rough order of value:

- **Deriving the other quarters.** A missing first, second or third quarter could
  be filled the same way, as the difference of two cumulative periods. Cash flow
  quarters are patchy for every company, so this would fill real gaps. Deferred
  because those gaps are a tagging choice rather than structural, and chaining
  subtractions needs two figures from two filings to agree.
- **Whether incoherence should force a `check` trust label.** It does not today:
  29 statements are labelled `reported` while carrying a line newer than the filing
  they were read from. The numbers are not in doubt there, only their provenance,
  but the opposite choice is defensible and is one clause.
- **A contiguity rule for duplicate period starts.** Adobe's 23 rows are resolved
  by majority of filings, which is a heuristic. The accounting correct test is
  whether a period starts the day after the previous one ends, which needs the
  period chain.
- **One definition of each accounting identity.** The balance sheet identity is now
  written in `consistency_balance_sheet` and in `mart_confidence_report`, on
  different inputs by design, and a third partial version lives in
  `int_facts_derived`. A macro could hold one definition.
- **Presentation lines that are not concepts**, such as a gross margin percentage
  or a grouping header. These would need a separate `config/statements.yml`; the
  concept order in `config/tag_mappings.yml` was enough without one.

Phase 6 (linkbase)
- Which filings to parse (for example latest 10-K per company).

Phase 7 (API)
- Hosting: local only, or a student credit host. Not a dependency of the pipeline.
