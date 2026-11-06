# Adding a company

[← back to the README](../README.md)

No code changes. Adding a company is three lines of YAML, a pipeline run, and
then reading the worklist the pipeline produces about it.

This page is the test of whether the project's central claim holds. If adding a
company needed a change to a Python file or a dbt model, the config and code
split would be a slogan rather than a design.

## 1. Find the CIK

Every SEC filer has a ten digit Central Index Key. Search for the company at
[sec.gov/cgi-bin/browse-edgar](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany),
or read it from the URL of any of its filings. Leading zeros do not matter in
config.

## 2. Add it to `config/companies.yml`

This is the real entry for one of the 28, copied from config:

```yaml
  - cik: 1650372
    ticker: TEAM
    name: Atlassian
    description: Team collaboration software (Jira, Confluence)
    group: rule_changer
    notes: XBRL data starts 2018; contains both ifrs-full and us-gaap facts
    events:
      - { year: 2015, note: IPO }
      - { year: 2023, note: First 10-K under US GAAP after IFRS 20-F filings }
```

Only `cik`, `ticker` and `name` are required. Everything else inherits from the
`defaults` block: `start_year: 2009`, no end year, enabled, and the six report
types that count as a financial report.

Override a default only when the company needs it:

```yaml
    start_year: 2019          # it listed later, so earlier years are empty
    report_types: [10-K, 10-Q, 20-F]   # it files a 20-F
    enabled: false            # keep the row, stop ingesting it
```

**`report_types` is the one to think about.** It decides which filings count as
a financial report. A proxy statement also carries XBRL and tags net income in
its pay versus performance table, often in millions and sometimes against the
wrong year. Proxies are filed after the annual report, so including one lets a
"latest filing wins" rule publish the wrong number.

## 3. Check the CIK before you ingest

```bash
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-check-ciks
```

This asks SEC whether each CIK in config is the company config claims it is. A
transposed digit in a ten digit number otherwise costs a full ingestion run
before anyone notices.

## 4. Run the pipeline

```bash
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-ingest
```

```bash
cd transform && uv run dbt build --profiles-dir . --target dev
```

Or just push the config change: the daily `ingest` workflow picks it up and the
rest of the chain follows.

## 5. Read the worklist

The pipeline tells you what it could not map, so you are never guessing:

```bash
curl -s '.../coverage?tickers=TEAM&status=missing'
```

```bash
curl -s '.../tags/unmapped?tickers=TEAM'
```

`mart_mapping_coverage` gives one row per company, concept and fiscal year with
a status. `mart_unmapped_tags` ranks the standard tags nobody has mapped yet.
`mart_custom_tags` lists the tags this company invented for itself.

Then add mappings or overrides **only for what it flags**. In practice most
companies need nothing: the existing rules already cover all 28 here, and the
nine revenue tags between them handle every one.

## 6. If it does need a rule

Three mechanisms, in increasing order of how much they claim:

**A global tag, in `config/tag_mappings.yml`.** Use this when the tag is a
standard one that other companies in the sector would also use. Add it in
priority order within the concept.

```yaml
      - { tag: "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax", confidence: high, note: "Used by CrowdStrike" }
```

**A `prefer` override**, when one company uses a tag nobody else does. Scoped to
a CIK and optionally a year range. It can introduce a tag that appears in no
global rule, and it defaults to `low` confidence so a single company judgement
never reads as a sector wide rule.

**An `ignore` override**, when a company uses a standard tag to mean something
else. This is stronger than ranking the tag last, because a tag ranked last
still wins whenever nothing above it matched. Always write the note: the
reasoning is the valuable part.

```yaml
  - cik: 1327811
    concept: operating_expenses
    ignore: ["us-gaap:OperatingExpenses"]
    note: >
      Workday uses this tag for a different concept than everyone else, and its own
      presentation label says so...
```

## 7. Confirm nothing else moved

```bash
cd transform && uv run dbt test --profiles-dir . --target dev
```

22 hand written tests check accounting identities, that quarters sum to the
year, that derived values match their inputs, and that every fact reaches the
mart. A new company that breaks one of those has found something, and the test
names say what.

## Deeper

Section 8.5 of [design.md](design.md) is the onboarding sequence, 10.2 the
override mechanisms in full, and 10.9 the coverage report and worklist.
[reconciliation.md](reconciliation.md) explains what the confidence levels
mean before you assign one.
