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
| 6 | Linkbase verification | Done. Presentation and calculation linkbases checked against every mapping |
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

## 13. Phase 6 as built: linkbase verification

Until this phase, confidence meant "a standard tag, used consistently across the
sector". It was an assertion about our own judgement, and section 10.5 promised that
Phase 6 would check it against the filings' own arithmetic. That is what this phase
does, and the result is that the mappings were right: the evidence confirmed them
rather than overturning them. The one large correction it produced came from the
other linkbase, the one that had been sitting unread in the raw layer since Phase 4.

### 13.1 The two linkbases

An XBRL filing is not one file. The instance document holds the numbers; separate
linkbases hold the relationships between tags.

| Linkbase | What it declares | Where it comes from |
|---|---|---|
| **presentation** | Which statement each tag appears on, in what order, under what label | **Already landed**: `pre.txt` in the Data Sets, 69 quarters of it |
| **calculation** | Children sum to a parent, each weighted plus or minus one | EDGAR filing directories. Not in the Data Sets |

Phase 4's ingestion had been landing `pre.txt` since it started and no model read it.
That was 118,675 rows covering 1,029 filings and 1,878 tags, free, and it turned out
to carry the single most valuable finding of the phase.

### 13.2 Fetching the calculation linkbases

**Where the list of filings comes from.** `submissions` looks like the obvious source
and is the wrong one. SEC puts only the most recent thousand filings in that
response, and Salesforce files about 172 documents a year, so its block covers
2023-08-23 to 2026-09-23: three years, and **3 of its 18 annual reports**. The
mappings most in need of evidence are historical. `companyfacts` carries the
accession and form on every fact, only for filings that reported XBRL, which is 74
filings for Salesforce and reaches 2010.

**Discovery.** A filing directory's `index.json` lists its files, and the calculation
linkbase is the one whose name ends `_cal.xml`. Matched on the name, not on the
`type` field, which reads `text.gif` for every file in that listing including the
XML. A plan that trusted `type` would have found nothing.

**Results.** 266 annual reports were attempted. **259 landed, 6 carry no calculation
linkbase at all, and 1 is not served by EDGAR.**

The 6 are not the old filings that were expected to be thin. They are the three most
recent annual reports of HubSpot and of Box, which is a caution rather than a
curiosity: the evidence source is disappearing for recent years at some filers,
while a 2010 Salesforce filing carries 89 arcs across 4 networks.

The 1 is `0001108524-21-000014`, a Salesforce 10-K filed 2021-03-17 that companyfacts
attributes 555 facts to and whose entire EDGAR directory returns 404. A 404 on a
filing directory is recorded as permanently unavailable rather than retried monthly,
counted separately and logged as a warning, so a systematic URL bug would appear as
259 unavailable rather than silently.

**Parsing.** `xml.etree.ElementTree` from the standard library. A linkbase is XLink:
each network declares locators naming concepts, then arcs joining two locator labels.
This is the first time the project derives anything outside dbt, which was a
deliberate line. The mitigation is that the raw XML is stored as published, so the
flattened form is always reproducible, and that paid off within a day. See 13.3.

### 13.3 A format version, and why the raw file is kept

Each end of an arc also records the schema its concept is declared in, because that
is what makes a tag custom, definitionally:

```
http://xbrl.fasb.org/us-gaap/2017/elts/us-gaap-2017-01-31.xsd#us-gaap_GrossProfit
crm-20180131.xsd#crm_SomethingCustom
```

A standard concept is referenced by absolute URL to the taxonomy that defines it. A
concept the filer invented is referenced relatively, because it is declared in the
filing's own schema in the same directory. No list of known prefixes is needed, and a
test asserts the two signals never contradict.

That field was added **after** the 259 filings had landed. `ARCS_FORMAT` is bumped
when the shape of `arcs.json` changes, and a run re-parses any filing whose stored
arcs are behind, reading the XML already in the bucket. All 259 were re-parsed in
about two minutes with **zero requests**. Keeping the raw file as published, rather
than only its flattened form, is what made that a two minute job instead of a
re-download.

### 13.4 The direction of an arc, which is the opposite of what it looks like

The parent of a calculation arc is **the line the filer computes**, not the larger
figure. Salesforce declares:

```
NetIncomeLoss = ProfitLoss (+1) - NetIncomeLossAttributableToNoncontrollingInterest (-1)
```

`ProfitLoss` is 69.7 million and `NetIncomeLoss` is 64.5 million for fiscal 2011, so
the child is larger than the parent. Any rule of the form "prefer the parent because
it is the total" is wrong about half the time, and the first draft of this phase's
plan contained exactly that rule.

The rule that survives is narrower: **where two tags mapped to the same concept stand
in a parent and child relationship, the child is not that concept's total.** Revenue
being a child of gross profit says nothing, because they are different concepts.

An apparent inconsistency this exposes, which is correct. For equity we take the
figure including noncontrolling interests; for net income the figure excluding them.
Balance sheet equity must include them or it will not balance against total assets,
which is why GitLab's JiHu joint venture of 45.5 million belongs there. Net income
for per share purposes excludes them, because those earnings do not belong to common
stockholders, which is what pairs it with our diluted EPS. Both happen to be the
calculation parent in their filings, and that is a coincidence of how filers
structure arithmetic rather than a principle.

### 13.5 Statement networks are not identifiable from role names

A filing carries about a hundred calculation networks and most are footnote detail.
Role names are the filer's own words: Salesforce wrote
`ConsolidatedStatementsOfCashFlows`, `StatementOfCashFlowsIndirect` and
`StatementConsolidatedStatementsOfCashFlows` across three years for the same
statement.

So nothing pattern matches role names. An arc counts as statement level when both of
its ends appear on a primary statement according to `pre.txt`, which already
classifies tags by statement. **20,914 of 45,647 arcs** are statement level by that
test.

### 13.6 What the evidence settled

`mart_calculation_evidence` holds one row per company, concept and candidate tag,
including the tags that lost a disagreement, because those are half of the question.

| Verdict | Rows |
|---|---|
| `confirmed_total` | **537** |
| `component_of_same_concept` | **5** |
| `no_arcs` | 0 |

All five contradictions are on the tag the config **rejected**:

| Companies | Concept | Tag the filer calls a component | Config prefers |
|---|---|---|---|
| CrowdStrike, Workday | net_income | `ProfitLoss` | `NetIncomeLoss` |
| Salesforce, CrowdStrike, Snowflake | total_equity | `StockholdersEquity` | the including NCI variant |

**The acceptance test.** Five tags are excluded from config by hand, each found in
Phase 3 by noticing a total that was too small or too large. Every one should be
visible in the filings' own arithmetic standing in a relationship to a line we map,
and if the engine cannot show that, it does not work. It is a dbt test rather than a
check run once, and it passes.

Its first version only looked one way, requiring each excluded tag to be an input to
a mapped line, and reported one failure.
`us-gaap:LiabilitiesAndStockholdersEquity` is a **root**: Autodesk computes it from
nine children, one of them `StockholdersEquity`, and it is an input to nothing at
all. The evidence that justifies excluding it runs in the other direction, so the
test now checks both. The acceptance test caught a flaw in itself, which is the best
thing it could have done.

### 13.7 Evidence beside confidence, joined per filing

`mart_financials` carries an `evidence` column, and the grain of its join is the
whole design.

Asking whether a company's linkbase has **ever** called a tag a component flags 115
published values. Asking whether **the filing that reported the number** calls it
one flags **24**. The 91 value gap is 75 values from 10-Qs, whose linkbases are not
fetched, and 16 from 10-Ks whose own arcs do not contain the relationship. Salesforce
had no noncontrolling interest in some years, so `StockholdersEquity` genuinely was
its total equity in those filings; the same tag was a component in others, exactly as
`SalesRevenueServicesNet` was a component for Salesforce in 2010 and the total in
2018. Aggregating across a company's filings would have published 91 false
accusations.

| `evidence` | Values |
|---|---|
| `unexamined`, the filing carries no linkbase | 16,817 |
| **`confirmed`** | **5,818** |
| `not_applicable`, no single source tag | 2,675 |
| `contradicted` | 24 |

**Only 23 percent of published values can be judged**, because two thirds come from
10-Qs. That was a deliberate cost decision and it caps what the phase can conclude.

Evidence and confidence turn out to answer different questions, which is the clearest
justification for the column: **463 values labelled only medium are confirmed by the
filer's own arithmetic, and 15,709 labelled high have no arithmetic behind them.**

The 24 contradicted values are Workday quarterly net income taken from `ProfitLoss`,
and all 24 are identical to the alternative to the dollar, because Workday has no
noncontrolling interest for the arithmetic to separate. A structural contradiction
with no numerical consequence, so `contradicted` is deliberately **not** folded into
the `trust` label; it is counted beside it.

### 13.8 What the presentation linkbase found that no arithmetic could

The largest correction in the project came from one label.

**Workday's operating expenses were overstated by exactly its cost of revenue, in 92
published values across 13 annual years.**

| Company | Label for `us-gaap:OperatingExpenses` |
|---|---|
| **Workday** | **"Total costs and expenses"** |
| Adobe, Autodesk, Box, Salesforce, CrowdStrike, Datadog, DocuSign, Elastic, Figma | "Total operating expenses" |

Workday alone uses that tag for a different concept, and says so in its own label.
This concept excludes cost of revenue, which is what the derivation and the
consistency test both assume, so the tag should not be used for Workday at all.

**The test that exists to catch this could not see it.**
`consistency_operating_income` required gross profit, operating expenses and
operating income all to be reported. Workday never tags gross profit, so its gross
profit is always derived, so Workday was excluded from the test for all 13 of the
years in which it was wrong. The test now distinguishes the three positions:
operating expenses must be reported because it is what is under suspicion, operating
income must be reported or it may have been derived from the very subtraction being
checked, and gross profit may be derived because deriving it from reported revenue
and cost makes the comparison sharper rather than circular.

Verified by compiling the widened test and running it against the data from before
the fix: **69 failures, all Workday, and 0 after.** A passing test after a fix is
indistinguishable from a broken test until that is done.

An `ignore` override leaves the value to be derived. 70 of the 92 become correct
derived values; the other 22 become gaps, because cost of revenue is itself missing
for 2014 to 2016. Trading 22 wrong numbers for 22 honest gaps is the project's own
principle, though it makes coverage look worse.

### 13.9 What the evidence changed, and what it did not

Four bounded company overrides and one new tag closed six coverage gaps, and the
bounds matter more than the overrides. Salesforce's `CostOfServices` changes role
mid history:

| Filing year | `CostOfServices` is a child of | Meaning |
|---|---|---|
| 2010 to 2013 | `CostOfRevenue` | a component |
| 2015 to 2018 | `GrossProfit` | the cost line itself |

The gaps were fiscal 2015 and 2016, filed inside that second window, so the override
runs `from_year: 2015` to `through_year: 2016`. Unbounded, it would have corrupted
2010 to 2013, which already publish correctly from `CostOfRevenue`. This is the first
time the project has evidence rather than judgement for where a year bound belongs.

| Company | Concept | Years | Tag | Value |
|---|---|---|---|---|
| Salesforce | cost_of_revenue | 2015, 2016 | `us-gaap:CostOfServices` | 1,289.3 / 1,654.5 |
| Okta | cost_of_revenue | 2016 | `us-gaap:CostOfServices` | 36.0 |
| Okta | revenue | 2016 | `us-gaap:SalesRevenueServicesNet` | 85.9 |
| Atlassian | revenue | 2019, 2020 | `ifrs-full:RevenueFromContractsWithCustomers` | 1,210.1 / 1,614.2 |

Every one comes back `evidence = confirmed`, so the arithmetic does not contradict
the overrides the evidence suggested.

**The Atlassian gross profit warning, and a wrong explanation corrected.** That
warning was attributed, repeatedly, to IFRS classifying costs elsewhere. It was a
restatement our mapping could not follow. Atlassian restated 2017 and 2018 under
IFRS 15 in its 2019 20-F:

| Vintage | Revenue | Cost | Gross profit | Internally consistent |
|---|---|---|---|---|
| 2018 20-F | 619.936 | 119.161 | 500.775 | yes |
| 2019 20-F, restated | **626.684** | 119.161 | **507.523** | yes |

Both are correct. The pipeline took the restated gross profit, because latest filed
wins, and the unrestated revenue, because the restated revenue tag was unmapped. The
6.748 million gap was two vintages mixed. The general lesson is stronger than the
specific fix: **an unmapped tag does not only create a gap, it can freeze one line at
a superseded value while the rest of its statement moves on.**

**A reverse identity.** Operating expenses were derived from operating income but not
the other way round. HubSpot's 2012 had a reported gross profit of 34.766 and
operating expenses of 53.506 with the line between them empty.

**A scale check, not an EPS identity.** Net income should be about diluted EPS times
diluted shares. As an identity it is useless: it legitimately fails for pre IPO
companies, whose EPS is computed on income attributable to common stockholders after
preferred accretion, and Figma's 2023 misses by 464 times the rounding allowance
without being wrong. Formulated as a **scale** check, with the tolerance scaled by
shares rather than by net income and a threshold of three orders of magnitude, it
isolates exactly six values and 500, 1000 and 5000 all give the same six. HubSpot
tagged its 2014 interim share counts in thousands while tagging the annual in units,
and Box did the same for its 2021 annual. The test reports them; correcting a filer's
units needs a per company scale mechanism the config does not have.

### 13.10 Measured results

Production run 37359104397, 2026-10-05: **367 dbt nodes, 364 pass, 3 warn, 0
errors**, and 169 Python tests.

| | |
|---|---|
| Calculation linkbases landed | 259 of 266 attempted |
| Arcs | **45,647** across 2,244 networks |
| Statement level arcs | 20,914 |
| Presentation rows | 118,675 across 1,029 filings |
| Published values | 25,334 |
| Coverage: missing cells | **12** of 5,056 |

The presentation candidate worklist shrank from 8 rows to 2 as the real candidates
were acted on. The two that remain are `us-gaap:CostsAndExpenses` for Intuit and
Workday, which is the noise the two condition rule was always going to leave: a
genuine total of something that is not one of our concepts.

Three standing warnings, all explained:

- Workday at 2012-01-31: pre IPO redeemable preferred stock that Workday never
  tagged, so the 170.9 million is absent from the source data.
- Intuit, four company years: its own quarterly figures sum to between 20 and 59
  million away from its annual figure, on restatement free years.
- Six diluted share counts tagged in thousands, per 13.9.

**Still open, both explained rather than outstanding.** Intuit's fiscal 2026 cost of
revenue, gross profit and operating expenses: its 10-K landed 2026-09-09 and tagged
no cost of revenue at all, and the Data Set quarter containing that filing is not
published yet, so these three should self heal. Workday's 2014 to 2016 cost of
revenue, gross profit and operating expenses: it reported two components with no
total, and one component is a custom tag that companyfacts drops entirely. Summing
them means giving the mapping layer a second fact source, with its own period
vocabulary, duplicate shapes and precedence rules against companyfacts. That is the
shape of `int_fsds_dimension_totals`, which needed six safeguards and still produced
the Autodesk bug, so it is a phase rather than a config edit.

### 13.11 Traps found while building

- **`true and null` is null.** `is_same_concept` came out null for 172 arcs whose
  child is unmapped, and a three valued flag would have dropped those arcs from every
  filter silently. Wrapped in `coalesce`.
- **A test fixture that did not match reality.** The linkbase fixture used relative
  hrefs for standard concepts, which no real filing does, so under the custom rule
  every concept in it looked like the filer's own. The new rule failed against the
  fixture rather than the data.
- **Jinja takes no `#` comments inside a `{% set %}` block.**
- **A new derived concept must be declared.** Adding the reverse operating income
  identity failed the `accepted_values` test on `int_facts_derived.concept`, which is
  that test working.
- **A measurement on the wrong grain over-flags by five times.** Company level
  evidence against filing level evidence: 115 against 24.
- **A passing test after a fix proves nothing** until it is run against the data that
  contained the error.
- **Backblaze's free tier allows 1 GB of downloads a day**, and five transform runs in
  an afternoon exceeded it, because every run re-reads the whole raw layer. Only
  `stg_sec_facts` is incremental. See section 14.

## 14. Running cost as built

Phases 2 to 6 added layers without anyone asking what a run cost, and the answer
turned out to be the binding constraint on how often the pipeline could run at all.
Three pieces of work fixed that, and they are recorded here rather than under a
phase because none of them changed what the project publishes.

### 14.1 What a run cost, and what it costs now

| Per transform run | Before | After |
|---|---|---|
| Raw layer files read | **535** | **0** on a day with nothing new |
| Warehouse downloaded | 92 MB | **15 MB** |
| Build and test step | 115s | 25s |
| Runs within the free daily allowance | about 8 | about 60 |

Backblaze's free tier stopped the pipeline twice in two days, once on the raw layer
and once on the warehouse fetch, with the same message naming both a bandwidth cap
and a transaction cap. The read count was the figure growing fastest: 69 Data Set
quarters times four files, plus 259 calculation linkbases, on every run.

### 14.2 Incremental staging

`stg_sec_facts` had been incremental since Phase 2 and the pattern was simple:
companyfacts snapshots carry a UTC timestamp in their path, so a processed file can
be excluded by path forever.

The Data Set and linkbase layers cannot use that pattern, and the reason is a
principle this project states but does not follow everywhere. Section 7.4 says raw
snapshots are written once and never overwritten. Data Set files land at a stable
path, `fsds/2013q3/num.tsv.gz`, and Phase 4's self healing **overwrites** a quarter
when a company is added whose history it should cover. `arcs.json` is overwritten
too, as the format bump in 13.3 did for all 259 filings. So a path that has been
read before may now hold different content, and excluding by path would silently
serve stale rows for a newly added company.

Versioning those paths would mean re-landing 69 quarters, which is 40 GB pulled from
SEC, so the ingestion jobs' own state files are the authority instead.
`stg_fsds_quarters` and `stg_linkbase_filings` expose `landed_at` per quarter and the
later of `fetched_at` and `reparsed_at` per filing. Five models became incremental
with `delete+insert` keyed on the quarter or the accession, each storing the version
marker it was built from, and the glob macros compare the two before deciding what to
read.

**`stg_fsds_tags` had to be split.** Its grain is one row per tag and declared
version, deduplicated across quarters, so it had nowhere to record which quarters it
had read. `stg_fsds_tags_by_quarter` is the incremental ledger at the three column
grain and `stg_fsds_tags` is now a view over it that dedupes back, so no consumer
changed and its uniqueness test still applies. That split exists only because an
incremental model needs a ledger of what it has processed and a deduplicated one
cannot carry it.

Measured on the five models, same work, same results:

| Model | Full refresh | Incremental |
|---|---|---|
| `stg_calculation_arcs` | 91.96s | 1.40s |
| `stg_fsds_facts` | 49.43s | 0.35s |
| `stg_fsds_presentation` | 42.59s | 0.29s |
| `stg_fsds_tags_by_quarter` | 40.70s | 0.39s |
| `stg_fsds_submissions` | 37.29s | 0.42s |

The transform workflow gained a `full_refresh` input, needed once for the transition
and useful afterwards for rebuilding from the raw layer.

### 14.3 Compressing the warehouse

With the raw layer costing nothing on a quiet day, the database fetch was the entire
read cost. A DuckDB file is mostly compressible: 92 MB stores as 15 MB.

Compression level was measured rather than assumed. The default costs 0.8 seconds to
compress and 0.1 to expand; level 1 saves four tenths of a second for 1.4 MB more,
and level 9 spends 2.2 seconds to save 0.1 MB.

Whether a stored copy is compressed is decided by reading its first two bytes rather
than by its name, so the key did not change and the switch needed no migration. Both
paths ran in production within five minutes of each other: the first run after the
deploy read the uncompressed copy the previous run had written and published a
compressed one, and the next read 15.0 MB.

### 14.4 Traps found

- **`depends_on` for every ref moved inside a conditional**, which broke five models
  at once. The fourth time this trap appeared in the project.
- **A missing column that presented as a join error.** The exclusion subquery read
  `max(landed_at)` from the target table, which on the run that first turned a model
  incremental predates that column. DuckDB resolved the name to an outer table
  instead, making the subquery correlated, and reported `LATERAL join cannot contain
  aggregates`. Columns in that subquery are now qualified so a missing one fails as
  what it is, and the macro checks with `adapter.get_columns_in_relation` whether the
  stored table can say what it has processed at all.
- **A local fixture cannot reproduce a schema that only exists in production.** The
  fixture passed all three scenarios, including a re-landed quarter, and production
  still failed on the first attempt, because the fixture built its tables fresh with
  the new columns present.
- **A log that reports a derived figure instead of the measured one.** After
  compression the fetch line still printed the size on disk, which is the expanded
  file and no longer what was transferred. `fetch_warehouse` now returns the bytes
  downloaded. This was the third time in the same stretch of work that a log said
  something true and useless.

## 15. Phase 7 as built: the API

### 15.1 What it serves

Eleven endpoints over the twelve published Parquet marts, in four groups: metadata
(`/`, `/companies`, `/concepts`, `/vocabularies`), the numbers (`/financials`,
`/statements/{statement}`), quality (`/confidence`, `/coverage`) and evidence
(`/evidence/{kind}`, `/tags/{kind}`). Plus `/healthz`.

The serving layer never opens the 92 MB database. It reads 1.4 MB of Parquet, and
DuckDB touches only the columns and row groups a query needs.

### 15.2 The layers, and why they are separate

`api/queries.py` holds the data layer and imports no web framework. `api/app.py`
holds HTTP and knows no SQL. The split is not tidiness: the filtering rules, the
year basis decision and the balance sheet translation are the parts most likely to
be wrong, and keeping them out of the routes means they are tested against a
Parquet fixture in milliseconds, with no server, and can be reused by the static
page in Phase 7's successor.

`api/asgi.py` exists only to hold the module level `app`. Opening the marts is file
I/O, and doing it during an import would make every test that imports the app module
depend on a directory of Parquet existing. In `asgi.py` failing fast is correct: a
serving process with no data should refuse to start.

### 15.3 The factory, which was forced rather than chosen

FastAPI reads a route's type annotations when the decorator runs, which is at import
time. Enums generated from the published data therefore have to exist *before* the
routes are declared, and a `lifespan` startup handler runs far too late. So the app
is built by `create_app(store)`, with the store opened by the caller. The side
benefit is that each test gets an app over its own fixture.

### 15.4 Documentation generated from config

Every parameter's description is assembled at startup from `mart_vocabularies`, as a
markdown list of value and meaning. The meaning of `derived` or `no_balance_sheet`
lives in `config/vocabularies.yml` and is never typed in Python. The ticker and
concept lists come from the data, so adding a company to config grows the
documentation with no code change. A test asserts that a sentence from config
appears in the OpenAPI document, so this cannot quietly regress into hand written
prose.

OpenAPI has no standard field for per value descriptions, only `enum` for the list
and `description` for the schema. The generated markdown list inside `description`
is the conventional workaround and renders correctly in Swagger and ReDoc.

Enums cover only the single value parameters (`period`, `year_basis`, `basis`, and
the path parameters). A comma separated list cannot be an enum, so `tickers`,
`concepts`, `confidence`, `evidence`, `status` and `trust` are documented strings
validated against the data, and an unknown value returns a 400 naming the valid set.

### 15.5 Decisions

**`year_basis` is unset rather than defaulted in the signature.** The default is
calendar, but `mart_mapping_coverage` has only `fiscal_year`, so it cannot serve a
calendar range. Had the default lived in the dataclass signature, coverage would
have rejected every request rather than only an explicit one. Unset now resolves to
the comparable label where a mart has one and to fiscal where it does not. On the
HTTP side `/coverage` simply does not offer the parameter, because advertising one
that could only ever fail is worse documentation than omitting it.

**The balance sheet translates `period`.** All 1,230 rows are instants, so there is
no annual balance sheet; `period=annual` means `is_year_end`. A caller asking for
the 2025 annual statements gets all three without knowing which is made of instants,
and the real `period_kind` is always in the response.

**Statement lines are an ordered array.** JSON object keys carry no order, and each
value belongs structurally beside its own confidence rather than being paired by a
`_confidence` naming convention the client has to know. The array is built by looping
over `mart_concepts`, so adding a concept to config grows it with no code change.

**Values are bound, identifiers are allowlisted.** SQL has no placeholder for a
column name, so binding alone cannot protect one. The single exception is the Parquet
path in `CREATE VIEW`, which DuckDB will not parameterise; it is quoted as SQL
expects and the mart name is checked against a plain identifier first.

**An absent mart is a 503.** Found while writing the tests: a mart the index did not
carry reached the reader as a DuckDB catalog error, which is a 500 saying nothing
actionable. It now names the missing mart and lists what is available. 503 because
the caller did nothing wrong and the data is incomplete.

### 15.6 Pagination

Offset and limit, defaulting to 1000 and capped at 10000, with `total_rows` always
reported. `next` and `previous` are built by replacing only the offset on the
incoming URL, so every other filter survives; the RFC 8288 `Link` header carries the
same thing for generic clients. Each endpoint has a fixed sort over columns unique
for its mart's grain, because offset paging without a deterministic order can overlap
or skip rows invisibly.

Cursor pagination is deliberately not used. Cursors solve rows shifting between page
requests, and the marts are rewritten once a day and never mutated in between.

### 15.7 Logging and the limiter

One structured JSON line per request to stdout, carrying the route template rather
than the raw URL so lines aggregate by endpoint. Without issued keys these count
requests and not people, which is accepted.

A token bucket per client address, 60 a minute by default, with `429` and
`Retry-After` and the `X-RateLimit-*` headers on every response. `/healthz`, `/`,
`/docs`, `/redoc` and `/openapi.json` are never limited, because a host whose health
checks hit a 429 kills the container. The bucket dictionary is swept and capped, or
it would grow without limit under addresses that never repeat.

Two limits on record: in process counters are correct at exactly one instance, and
IP keying punishes shared addresses. It is a guard against a runaway script, not a
security control. Correct distributed limiting needs shared state, which costs money.

### 15.8 A trap found while verifying the proxy configuration

**uvicorn trusts `X-Forwarded-For` by default.** `proxy_headers` defaults to `True`,
and `forwarded_allow_ips` defaults to `127.0.0.1` (overridable through the
`FORWARDED_ALLOW_IPS` environment variable). The `--proxy-headers` flag does not turn
the behaviour on; it is already on.

Measured, with a bucket of three:

| Launch | Four distinct `X-Forwarded-For` values |
|---|---|
| `--proxy-headers --forwarded-allow-ips="*"` | four separate buckets |
| no flags, requests from 127.0.0.1 | four separate buckets, because 127.0.0.1 is trusted by default |
| no flags, four plain requests | one shared bucket, fourth request 429 |

So the dangerous setting is `--forwarded-allow-ips="*"`, which trusts the header from
whoever sent it: any caller who can reach the port directly can forge an address and
the limiter stops limiting. The correct setting is the proxy's own address. Where
nothing is in front, `--no-proxy-headers` is safer.

Left unset behind a real proxy, every caller looks like the proxy and the limiter
puts the whole world in one bucket. Both failures are quiet, which is why the
Dockerfile documents the choice rather than picking one.

### 15.9 The container

Two stages. The first fetches the marts with the bucket credentials mounted as build
**secrets**, which leave nothing in a layer, rather than build arguments, which are
recorded in the image history for anyone who pulls it. The second copies the
application and the marts into a slim runtime image that runs as a non root user and
holds no credentials at all.

The Parquet is baked in rather than fetched at boot, so a cold start is a local file
open and costs the same whether the host bills by the hour or by the request. That is
affordable only because Phase 5 chose Parquet: 1.4 MB fits in an image, 92 MB of
DuckDB would not.

`--host 0.0.0.0`, because the default of 127.0.0.1 accepts connections only from
inside the container and the host's health check never arrives.

**Not built or measured here**: this machine has no container runtime, so the
Dockerfile is written and reviewed but has never been run. Its size and start time
are unverified.

### 15.10 Measured

| | |
|---|---|
| Query layer, one company and concept | 4.3 ms |
| Query layer, every annual value | 9.4 ms |
| Over HTTP, including serialization | 7 to 13 ms |
| Published marts | 12 files, 1.4 MB |
| Tests | 264 Python, 422 dbt nodes |

Verified over HTTP against production: Salesforce fiscal 2026 revenue 41,525m with
four quarters summing to it, the fourth derived; Workday fiscal 2015 cost of revenue
264,803,000 at medium confidence naming both summed tags; Atlassian fiscal 2019
revenue 1,210.127m under IFRS, confirmed by the filing's own arcs.

### 15.11 Not done

No host is chosen, so nothing is deployed and no workflow builds or publishes the
image. The static DuckDB-WASM page needs the repository to be public and is still
outstanding. `format=csv` is deferred. `raw/config/` still has no lifecycle rule.

## 16. Open decisions for later phases

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

Phase 6 (linkbase): built, see section 13. Every annual report was parsed rather
than the latest per company, because the mappings needing evidence are historical.

Left open by Phase 6, in rough order of value:

- **Per concept `label_hints` in config.** Declaring the labels a concept expects
  would let the engine question mappings it already has. This was deferred during
  Phase 6 on the grounds that reading an eight row candidate list costs less than
  maintaining a heuristic, which was true for candidate detection and wrong for the
  larger case: Workday's operating expenses were overstated in 92 values because it
  labels `us-gaap:OperatingExpenses` "Total costs and expenses" while every other
  filer labels it "Total operating expenses". A declared expectation would have
  caught that automatically rather than by investigation. See 13.8.
- **Fetching 10-Q calculation linkbases.** Two thirds of published values come from
  10-Qs, so only 23 percent of values can currently be judged. This would roughly
  triple coverage at roughly triple the requests.
- **A per company scale override.** Six diluted share counts are tagged in thousands
  by filers who tag the annual in units. The scale check reports them; nothing can
  correct them, because config has no notion of a unit multiplier.
- **Custom tags beyond a declared sum.** Workday's six gaps are closed: a third
  override mode, `sum`, adds named parts from the Data Sets where one part is a
  custom tag that companyfacts drops, scoped to one company because a custom tag name
  is not unique. What is still open is the general case. The sum has to be declared
  per company and per concept, so a filer who reports a concept only as custom parts
  is found by inspection rather than by the pipeline. `mart_custom_tags` lists 1,092
  unmapped custom tags; nothing proposes which of them are parts of a total we are
  missing. The calculation linkbase could: a custom tag whose parent is a concept we
  map is a declared part of it.
- **Recovering the schema href authoritatively for older runs.** Already done by the
  format bump, and recorded here only because the mechanism generalises: any future
  change to the parsed shape is a version bump and a re-parse, with no refetch.

Running cost: addressed, see section 14. Incremental staging, warehouse
compression, and a `full_refresh` switch for rebuilding.

Left open by that work:

- **The never overwritten principle is still violated in two layers.** Section 7.4
  says raw snapshots are written once; Data Set quarters and `arcs.json` are
  overwritten in place, which is why the staging models compare against the
  ingestion jobs' state rather than against file paths. Versioning those paths would
  cost 40 GB of re-landing from SEC, so it stays as it is, documented rather than
  fixed.
- **The `stg_fsds_tags` split is a workaround.** A model whose grain deduplicates
  across the thing it reads cannot record what it has read, so it is now two models.
  Any future deduplicating staging model will meet the same wall.
- **The warehouse fetch is still the whole read cost**, now 15 MB rather than 92.
  Smaller still would mean publishing only the tables the incremental logic needs to
  resume rather than the entire database, which is a real option and not obviously
  worth the complexity.

Phase 7 (API)
- Hosting: local only, or a student credit host. Not a dependency of the pipeline.
