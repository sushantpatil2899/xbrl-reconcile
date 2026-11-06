# Evidence

[← back to the README](../README.md)

## What this does

Checks every mapping against the filings' own declared arithmetic. Confidence
says "this is the standard tag for this concept across this sector". Evidence
says "and the company's own filing agrees". They are different claims and they
disagree often enough to be worth keeping apart.

When a company files XBRL it can also file a **calculation linkbase**: a machine
readable statement of which tags it adds up to produce which other tags. That
is the filer declaring, in its own words, that `CostOfRevenue` plus
`GrossProfit` equals `Revenues`. If our config maps a tag to a concept, and the
filer's own arithmetic treats that tag as a *part* of something we also call
that concept's total, the mapping is worth a second look.

The pipeline parses **45,647 declared calculation relationships from 255 annual
reports**, and judges every published value against the filing that reported it.

## How it works

Four outcomes, decided per filing and per period, never per company:

| Verdict | Values | Share | What it means |
|---|---:|---:|---|
| `confirmed` | 21,910 | 82.0% | That filing's own arithmetic does not contradict the mapping |
| `not_applicable` | 3,928 | 14.7% | No single source tag: derived, a component sum, or recovered from dimensions |
| `unexamined` | 860 | 3.2% | That filing carries no calculation linkbase |
| `equivalent` | 27 | 0.1% | The filer calls the tag a part, and its own figures make the part equal the total |
| `contradicted` | 0 | 0% | The filer calls it a part and its own figures make the part smaller |

The 860 unexamined values split 721 from quarterly reports and 139 from annual
ones. Quarterly linkbases are deliberately not fetched; the annual ones are
filings that genuinely shipped without a calculation linkbase. Saying
`unexamined` rather than `confirmed` is the whole point of the column: an
absence of evidence is not evidence.

At the mapping level rather than the value level, 543 candidate tag and concept
pairs were examined. 537 are `confirmed_total`. Six are
`component_of_same_concept`, and they are the interesting ones:

| Company | Concept | Tag the filer calls a part | Periods differing | Periods equal |
|---|---|---|---:|---:|
| CRWD | net_income | `us-gaap:ProfitLoss` | 60 | 11 |
| CRWD | total_equity | `us-gaap:StockholdersEquity` | 53 | 9 |
| SNOW | total_equity | `us-gaap:StockholdersEquity` | 24 | 4 |
| WDAY | net_income | `us-gaap:ProfitLoss` | 14 | 89 |
| CRM | total_equity | `us-gaap:StockholdersEquity` | 11 | 1 |
| SPLK | revenue | `us-gaap:Revenues` | 0 | 0 |

Both patterns are real accounting, not bugs. `StockholdersEquity` excludes
noncontrolling interests, so it is genuinely a part of total equity for a
company that has them and genuinely the whole thing for a company that does
not. `ProfitLoss` is profit before the accretion on redeemable preferred stock.

## Decisions worth knowing

**Being declared a part is not a contradiction on its own.** This was the first
version of the check and it was wrong. Where a company has no noncontrolling
interest, the part and the total carry the same number, so the arc exists but
nothing is in doubt. The check therefore compares the period's own figures, not
the shape of the arc. That distinction is why `equivalent` exists as a separate
verdict from `contradicted`, and why the count of genuine contradictions is
currently zero rather than 27.

**Nothing measurable is not the same as equal.** Splunk's `Revenues` is declared
a part in a filing that reports no figure for it, so both counts are zero.
Testing `periods_differing = 0` alone would call that equal, which reads an
absence of measurement as a result. It is `component_of_same_concept` instead.

**Evidence is judged per filing, never per company.** A tag can be a total in one
year and a component in the next for the same filer. Salesforce's
`StockholdersEquity` genuinely was its total equity in some years and a
component in others. Asking whether a company *ever* declared a relationship
flags 115 values; asking whether *the filing that reported the number* declares
it flags 24. Only the second question is about the number in front of you.

**Evidence never silently rewrites confidence.** A parser quietly downgrading a
published value would defeat the purpose of publishing the claim. The two labels
sit beside each other and the reader can see both.

## Verify

Every published value carries its verdict:

```bash
curl -s 'https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/evidence/calculation?limit=10'
```

Reproduce the verdict table against the published Parquet:

```sql
select evidence, count(*) n, round(100.0 * count(*) / sum(count(*)) over (), 1) pct
from 'https://sushantpatil2899.github.io/xbrl-reconcile/mart_financials.parquet'
group by 1 order by n desc;
```

## Deeper

Section 13 of [design.md](design.md) is linkbase verification as built: 13.1 the
two linkbases, 13.4 why an arc points the opposite way to how it reads, 13.7 why
evidence sits beside confidence, 13.9 what the evidence changed and what it did
not, and 13.12 the full account of why a declared part is not always a smaller
number.
