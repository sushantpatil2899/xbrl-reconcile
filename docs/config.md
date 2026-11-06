# Config

[← back to the README](../README.md)

## What this does

Three YAML files decide what the pipeline ingests, what the tags mean, and what
values the pipeline is allowed to produce. No ticker, CIK, tag name or year
appears anywhere in the Python or the SQL. Adding a company is a config edit;
adding a concept is a config edit; changing the order lines appear on a
statement is a config edit.

| File | Decides |
|---|---|
| `config/companies.yml` | Which companies, from which year, and which SEC forms count as a report |
| `config/tag_mappings.yml` | Which raw XBRL tags mean which canonical concept, and how much to trust each |
| `config/vocabularies.yml` | The closed sets of values the pipeline may produce, and what each value means |

## How it works

**`companies.yml`** has a `defaults` block and a list of companies. Any default
can be overridden per company. Facts the SEC already publishes, such as fiscal
year end, former names and industry code, are read from SEC data rather than
repeated here.

```yaml
defaults:
  start_year: 2009
  report_types: [10-K, 10-K/A, 10-Q, 10-Q/A, 20-F, 20-F/A]

companies:
  - cik: 796343
    ticker: ADBE
    name: Adobe
    group: old_timer
    notes: 52/53 week fiscal year ending near November 30
```

`report_types` matters more than it looks. A proxy statement also carries XBRL
and tags net income in its pay versus performance table, often in millions and
sometimes against the wrong year. Proxies are filed after the annual report, so
a naive "latest filing wins" rule reads the proxy. Only the forms listed here
count as a report.

**`tag_mappings.yml`** maps raw tags to concepts. The order of `tags` is the
priority: the first tag a company actually reported for a period wins.

```yaml
concepts:
  revenue:
    statement: income_statement
    unit: USD
    tags:
      - { tag: "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", confidence: high }
      - { tag: "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax", confidence: high, note: "Used by CrowdStrike" }
      - { tag: "us-gaap:Revenues", confidence: high }
      - { tag: "us-gaap:SalesRevenueNet", confidence: medium, note: "Retired in 2018 when ASC 606 took effect" }
```

The order of concepts in this file is also the order they appear on the
published statement, and the statement columns are generated from it. A
statement is reordered by moving a block of YAML.

**`vocabularies.yml`** declares every closed set of values: confidence levels,
evidence verdicts, period kinds, units, accounting basis, coverage statuses and
the rest. The dbt models are tested against this file, and the API generates its
parameter documentation from the descriptions in it, so a value cannot reach a
caller without an explanation attached.

## Decisions worth knowing

**A component tag is absent, not ranked last.** A tag that means part of a total
is simply not listed for that concept. Ranking it last would not help, because a
tag ranked last still wins whenever nothing above it matched, which is exactly
the case where the company reported only the part.

**Confidence in this file is a claim about the tag, not about the number.** It
says "this is the standard tag for this total across this sector", not "the
filing's own arithmetic agrees". That second question is answered separately in
[evidence.md](evidence.md), and the two disagree often enough to be worth keeping
apart.

**Per company overrides exist but are deliberately narrow.** A `prefer` override
can introduce a tag that is in no global rule, which is how a company reporting
something nobody else uses gets mapped. An `ignore` override removes a tag from
consideration for one company entirely. Both are scoped to a CIK and a year
range, and an override defaults to `low` confidence so a one company judgement
can never read as a sector wide rule.

## Run it yourself

```bash
SEC_CONTACT_EMAIL=you@example.com uv run xbrl-check-ciks
```

Checks every CIK in `companies.yml` against SEC's own records, so a typo in a
ten digit number is caught before it becomes a day of empty ingestion.

```bash
uv run pytest tests/test_companies_config.py tests/test_tag_mappings_config.py tests/test_vocabularies.py
```

The config files are validated by the test suite on every push, which is why the
`ci` workflow points at config in the architecture diagram.

## Verify

Every published value names the tag it came from, so the config is checkable
from the outside:

```bash
curl -s 'https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/concepts' | head -40
```

## Deeper

Section 7.1 of [design.md](design.md) covers the companies file, section 8.4 the
tag mapping shape, section 10.2 the override mechanisms, and section 15.4 how the
API documentation is generated from the vocabularies.
