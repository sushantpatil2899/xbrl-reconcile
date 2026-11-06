# Reconciliation

[← back to the README](../README.md)

## What this does

Turns a raw XBRL tag into a canonical concept and attaches a confidence level
to the result. This is the part of the project the rest exists to serve.

The measured shape of the problem, across the 28 companies here: **16 canonical
concepts are reported under 58 distinct source tags.** Revenue alone accounts
for nine of them.

| Tag used for `revenue` | Companies | Values | Confidence |
|---|---:|---:|---|
| `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | 26 | 1,228 | high |
| `us-gaap:Revenues` | 12 | 427 | high |
| `us-gaap:SalesRevenueNet` | 5 | 145 | medium |
| `us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax` | 1 | 52 | high |
| `us-gaap:SalesRevenueServicesNet` | 1 | 6 | medium |
| `ifrs-full:RevenueFromContractsWithCustomers` | 1 | 4 | medium |
| `ifrs-full:Revenue` | 1 | 1 | medium |
| `derived:annual-nine_month` | 28 | 198 | derived |
| `derived:half-quarter` | 1 | 1 | derived |

The company counts add to more than 28 because companies change tags across
years. `SalesRevenueNet` was retired in 2018 when ASC 606 took effect, so a
query written for today's tag silently returns nothing for the years before it.

## How it works

One filed fact walks through six decisions. The diagram of this is in the
README; the logic is below.

**1. Does config map this tag?** The fact joins to `config/tag_mappings.yml` on
the tag. A company level `ignore` override can remove a tag from consideration
entirely, which is different from ranking it last. A tag with no rule publishes
nothing and is listed in `mart_unmapped_tags` as something worth mapping next.

**2. Was a total tagged at all?** Three fallbacks, in order: sum the components
the filer reported separately, recover the total by summing one dimension from
the quarterly Data Sets, or sum the Data Set parts. Each enters the next step as
an ordinary candidate carrying `medium` confidence, never `high`.

**3. Rank the candidates.** Priority is the order in config. The runner up is
kept, not discarded, so a disagreement can be inspected rather than merely
counted.

**4. Do the top two agree?** Within one tenth of one percent, the choice did not
matter and the configured confidence stands. If they differ by more, a side was
picked, and confidence drops exactly one level: high becomes medium, medium
becomes low. 28 of 5,056 coverage cells are `ambiguous` for this reason.

**5. Which filing wins?** Several filings report the same period. US GAAP is
preferred over IFRS deliberately, not by filing date. Atlassian reports 2021
under both, and its 10-K happens to be filed later than its 20-F, so recency
alone would give the right answer by accident and the wrong one the moment the
order flipped. Within one basis, the latest filed figure wins, and the first
reported figure is kept beside it so a rewrite of history stays visible.
1,008 of 26,725 published values were restated at least once.

**6. Nothing anywhere?** The value is computed from an accounting identity or
from adjacent periods, and carries `confidence: derived`. The arithmetic is
exact; what it rests on is recorded separately as `inputs_confidence`.

## What comes out

Across 26,725 published values:

| Confidence | Values | Share | What it means |
|---|---:|---:|---|
| high | 21,121 | 79.0% | A standard tag for this concept, reported by the company itself |
| derived | 3,799 | 14.2% | Computed from other concepts, never reported |
| medium | 1,805 | 6.8% | A retired tag, another rulebook's tag, or a total reassembled from parts |
| low | 0 | 0% | A judgement call for one company. None currently resolves this way |

Coverage, over all 5,056 company and fiscal year and concept cells:

| Status | Cells | Share |
|---|---:|---:|
| reported | 4,629 | 91.6% |
| not_applicable | 228 | 4.5% |
| derived | 89 | 1.8% |
| no_balance_sheet | 82 | 1.6% |
| ambiguous | 28 | 0.6% |
| missing | 0 | 0% |

The 82 `no_balance_sheet` cells can never be filled. US rules require three
years of income statements but only two of balance sheets, so a company's
earliest fiscal year has no balance sheet to read. Labelling that as a
structural gap rather than as missing data is the point of having the status at
all.

## Decisions worth knowing

**Confidence is about the tag, not about the number.** A `high` value can still
be wrong if the filer made an error; a `medium` value is usually exactly right.
The label says how the value was obtained, which is a different question from
whether it is true. The second question is answered by
[evidence.md](evidence.md).

**The same standard tag can mean different things to different filers.** Workday
labels `us-gaap:OperatingExpenses` "Total costs and expenses" on its own income
statement; every other company here labels it "Total operating expenses".
Workday's figure therefore includes cost of revenue and the others' do not.
Reading that tag the same way for everyone overstated Workday's operating
expenses by exactly its cost of revenue, across 92 published values and 13
years. The fix was a company scoped override, which is what overrides are for.

## Verify

Pick any value and ask the API which tag it came from:

```bash
curl -s 'https://ca-xbrl-reconcile-api.wonderfulwater-66905cf2.northcentralus.azurecontainerapps.io/financials?tickers=CRWD&concepts=revenue&from_year=2024&to_year=2024'
```

Or reproduce the revenue table above against the published Parquet:

```sql
select source_tag, count(distinct cik) companies, count(*) n, min(confidence) confidence
from 'https://sushantpatil2899.github.io/xbrl-reconcile/mart_financials.parquet'
where concept = 'revenue'
group by 1 order by companies desc, n desc;
```

## Deeper

Section 10 of [design.md](design.md) is mapping and confidence as built, 10.4
the resolution rules, 10.5 the confidence model, 10.6 the deliberate exclusions,
10.8 the traps found, and 11.4 how a total is recovered by summing a dimension.
