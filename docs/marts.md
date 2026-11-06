# The marts

[← back to the README](../README.md)

## What this does

Twelve published tables, 60,275 rows, 1,397 KB of Parquet. That is the whole
output of the project. Everything the API serves and everything the query page
shows comes from these twelve files, and they are public, so any of it can be
checked without asking permission.

## The twelve tables

| Table | Rows | What it holds |
|---|---:|---|
| `mart_financials` | 26,725 | The published facts: one row per company, concept and period, with the latest figure, the originally reported one, and the figure from a filing a whole statement can be read from |
| `mart_unmapped_tags` | 11,024 | Standard tags nobody has mapped yet, ranked as a worklist |
| `mart_confidence_report` | 5,372 | One row per statement, saying what it is made of rather than what it says |
| `mart_mapping_coverage` | 5,056 | What is mapped and what is not, per company, concept and fiscal year |
| `mart_mapping_evidence` | 5,018 | What each filing's presentation linkbase says about where a tag belongs |
| `mart_income_statement` | 2,081 | Income statement, one column per line, in config's order |
| `mart_cash_flow` | 2,055 | Cash flow, cumulative as filers report it, with derived fourth quarters |
| `mart_balance_sheet` | 1,236 | Balance sheet, one row per reporting date because its lines are instants |
| `mart_custom_tags` | 1,103 | Tags each company invented, from the quarterly Data Sets |
| `mart_calculation_evidence` | 543 | Whether each filer's own arithmetic supports each tag we considered |
| `mart_vocabularies` | 46 | Every value the pipeline can produce, with what it means |
| `mart_concepts` | 16 | The canonical concepts, their statement, order and unit |

Measured 2026-11-06. The current counts are always in
[`_index.json`](https://sushantpatil2899.github.io/xbrl-reconcile/_index.json).

## How it works

**Statement columns are generated from config.** `mart_income_statement` does
not list its columns in SQL. A macro reads `config/tag_mappings.yml` and emits
one column per concept, in the order that file lists them, each paired with a
confidence column. Adding a concept adds a column. Reordering the statement is
a YAML edit.

**Two vocabularies are published as data.** `mart_concepts` and
`mart_vocabularies` are projections of the config files. Publishing them means
the API's parameter documentation, the page's dropdowns and the reader's own
queries all describe the same values with the same words, generated once rather
than written three times.

**Three marts are worklists, not results.** `mart_unmapped_tags`,
`mart_mapping_coverage` and `mart_custom_tags` exist to say what is *not*
covered. 11,024 unmapped tag rows is not a failure, it is the honest size of
the long tail, and it is ranked so the next useful mapping is at the top.

## Decisions worth knowing

**A statement is published twice over.** Each line carries its latest figure and
the figure from one filing that reported the whole statement. A company can
restate one line of an old balance sheet and never republish the rest, so a
statement assembled purely from latest values can fail its own accounting
identity while every individual number is correct. `is_coherent` and
`identity_holds` are separate columns for exactly this reason: together they
separate a wrong mapping from lines that came from different filings.

**`trust` summarises a whole statement in one word**, from its lines:

| trust | Statements | Meaning |
|---|---:|---|
| `reported` | 3,343 | Every line is a standard tag the company filed |
| `computed` | 1,046 | Contains a value derived from an identity or adjacent periods |
| `mapped` | 763 | Contains a weaker tag: retired, another rulebook, or recovered |
| `check` | 220 | An identity fails, a line was ambiguous, or a line is newer than the filing |

220 statements out of 5,372 are worth a second look, and the mart says which
220. That count spans every period kind; of the 632 annual statements alone, 26
are flagged. An output that can state its own weak spots is a stronger claim
than one that cannot answer the question.

**Parquet, not a served database.** 1,397 KB for all twelve against a 92 MB
DuckDB file. Because Parquet supports range requests, reading one income
statement costs about 100 KB and no server at all. That single fact is what
lets the API run at zero replicas and the query page run with no backend.

## Verify

```sql
select trust, count(*) n
from 'https://sushantpatil2899.github.io/xbrl-reconcile/mart_confidence_report.parquet'
group by 1 order by n desc;
```

```bash
curl -s https://sushantpatil2899.github.io/xbrl-reconcile/_index.json
```

## Deeper

Section 12 of [design.md](design.md) is the marts as built: 12.4 statement
coherence, 12.6 each mart in turn, 12.7 publishing them, and 12.9 the traps
found while building them.
