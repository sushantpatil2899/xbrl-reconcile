# Transform

[← back to the README](../README.md)

## What this does

dbt on DuckDB turns the raw layer into twelve published tables, in three
layers. 458 dbt nodes in total: 18 staging models, 11 intermediate models,
12 marts, 13 macros, and 22 hand written tests on top of the generated ones.

The whole thing runs on a GitHub Actions runner in minutes and leaves behind a
92 MB database and 1,397 KB of Parquet. There is no warehouse to pay for.

## How it works

**Staging** flattens the nested JSON into one clean row per fact, typed, with
no business logic. It keeps every version of every fact, because restatements
are data rather than noise and deduplicating here would throw away the evidence.
Bad rows are quarantined rather than dropped. Staging is incremental: each model
records which source files it has already read, so a quiet day reads nothing.

**Intermediate** is where the real work happens. The chain is:

| Model | What it decides |
|---|---|
| `int_facts` | Which facts are in scope at all |
| `int_facts_mapped` | Which tag means which concept, and what confidence that carries |
| `int_facts_resolved` | Which filing wins when several report the same period |
| `int_periods` | The period spine: fiscal and calendar year labels |
| `int_facts_quarterly` | Quarters, including the fourth, which nobody files |
| `int_facts_derived` | Values computed from an identity or from adjacent periods |
| `int_calculation_arcs` | The filers' own declared arithmetic |
| `int_arc_separation` | Whether a declared part really differs from its total |
| `int_fsds_component_totals` | Totals reassembled from components a filer reported separately |
| `int_fsds_dimension_totals` | Totals recovered by summing one dimension |
| `int_statement_filings` | Which single filing reported a whole statement |

The mapping and confidence logic is the heart of the project and has its own
page: [reconciliation.md](reconciliation.md). The linkbase work has
[evidence.md](evidence.md).

**Marts** are the twelve published tables, described in
[marts.md](marts.md).

## Decisions worth knowing

**A fiscal year is not a calendar year.** Sixteen of these twenty eight
companies end their year in January, so one fiscal label can span 335 days.
Every period therefore carries two labels: what the company itself calls the
year, and the calendar year most of it falls in. Comparing companies needs the
second; checking a figure against a filing needs the first. No period is ever
relabelled onto a quarter it did not report.

**The fourth quarter is derived, and says so.** Companies file three quarterly
reports and then an annual report covering the whole year. There is no Q4
filing. Q4 is annual minus nine month, it carries `confidence: derived` and the
source tag `derived:annual-nine_month`, and the four quarters sum to the annual
figure. 198 of the published revenue values are this.

**A computed value is never dressed up as a reported one.** Totals recovered by
summing a company's own components carry their own confidence level, and the
identity used is recorded in `source_tag` alongside the number.

**A statement is published twice over.** Each line carries both its latest
figure and the figure from one filing that reported the whole statement. A
company can restate one line of an old balance sheet and never republish the
rest, so a statement assembled purely from latest values can be internally
inconsistent while every individual number is correct.

**Every vocabulary is tested against config.** The `declared_in_vocabulary`
test checks that a column only ever contains values declared in
`config/vocabularies.yml`. A new value cannot appear in the output without
someone writing down what it means.

## Run it yourself

Against a local copy of the raw layer, no credentials needed:

```bash
cd transform && RAW_ROOT=/path/to/raw uv run dbt build --profiles-dir . --target dev
```

To list every node without building anything:

```bash
cd transform && uv run dbt list --profiles-dir . --target dev | wc -l
```

## Verify

The row counts of all twelve tables are published:

```bash
curl -s https://sushantpatil2899.github.io/xbrl-reconcile/_index.json
```

Measured on 2026-11-06: 60,275 rows across twelve tables, 1,397 KB of Parquet.

## Deeper

Section 9 of [design.md](design.md) is the staging layer as built, section 12
the marts, 12.2 the fiscal year problem, 12.3 the fourth quarter, 12.4 statement
coherence, and 14.2 the incremental work that cut the daily cost.
