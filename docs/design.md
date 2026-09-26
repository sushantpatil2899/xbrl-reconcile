# xbrl-reconcile: Design

Status: Phases 0, 1, 2 and 3 built. Later phases list open decisions only.
Last updated: 2026-09-25

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

## 11. Open decisions for later phases

Phase 3 (mapping)
- Initial canonical concept list (about 15).
- Tag mapping file format (YAML with generated dbt seed, or CSV seed directly).
- Priority when a company reports several candidate tags for the same period.

Phase 4 (custom tags)
- Which quarters of Financial Statement Data Sets to pull and how to filter.
- The Data Sets also carry dimensional facts, which companyfacts drops. That is
  the only route to Workday's cost of revenue and Intuit's post 2018 expense
  detail, 53 of the 62 remaining coverage gaps.

Phase 5 (marts)
- Fiscal year versus calendar year alignment for cross company comparison.
- Deriving Q4 as full year minus nine month year to date.
- Surfacing latest filed and originally reported values side by side, per the
  decision in section 8.6.
- **Statement coherence.** Resolving each concept independently by latest filed
  date means one statement can mix filings. Salesforce at 2017-01-31 takes assets
  and liabilities from the 2018 10-K and equity from the 2020 one, because the
  ASC 606 adoption adjusted opening equity without restating the prior balance
  sheet. 26 periods across 10 companies do not balance for this reason, and the
  consistency test warns on them. The options are per concept latest filed (today),
  statement level resolution from a single filing, or publishing both views. The
  choice depends on what the mart is for, so it belongs with the marts. Nothing is
  lost either way: int_facts_mapped keeps every filing's version.

Phase 6 (linkbase)
- Which filings to parse (for example latest 10-K per company).

Phase 7 (API)
- Hosting: local only, or a student credit host. Not a dependency of the pipeline.
