Comparable financial statements for 28 software companies, drawn from their own SEC
filings, with how sure we are about every single number published beside it.

## Why this is harder than it sounds

Since 2009, companies filing with the SEC have had to tag every number in their
financial statements in **XBRL**, a format where `revenue` is not a label on a page
but a machine readable tag drawn from a standard dictionary called `us-gaap`.

The catch is that companies are allowed to invent their own tags whenever they feel
the standard ones do not fit. So "revenue" is not one tag but many: one company uses
`us-gaap:Revenues`, another `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`,
a third something it made up itself. The same company changes which tag it uses from
year to year, after a merger or an accounting policy change. Some companies never
report a total at all and file only its parts.

This makes genuine comparison across companies and years a real problem rather than a
formatting inconvenience. Mature tooling in this area says outright that normalising
taxonomies at scale is where it gets hard.

## What this API does about it

It maps the tags companies actually used back onto **16 canonical concepts**, and
publishes **how confident that mapping is for every value**, along with the tag it
came from and what the filing's own arithmetic says about it.

Nothing here hides a judgement. A number assembled from two components says so. A
number computed rather than reported says so. A number whose tag the filing's own
calculation linkbase contradicts says so, and is still returned, because a
contradiction is a reason to look rather than a reason to withhold.

## How to read a value

Four fields travel with every number, and they answer different questions:

- **`confidence`** says how the value was obtained. `high` is a standard tag the
  company filed. `medium` is a weaker claim: a retired tag, another rulebook's tag,
  or a sum of parts. `low` is a judgement call for one company. **`derived` is not
  simply worse than `medium`**: it means the number was computed by exact arithmetic
  rather than reported, so the arithmetic is certain and what it rests on is
  `inputs_confidence`.
- **`source_tag`** is the XBRL tag behind the number. Several tags joined by `+`
  means the value is their sum. A `derived:` prefix means arithmetic, not a tag.
- **`evidence`** is what the filing's own calculation linkbase says about that tag.
- **`basis`** is which rulebook the filing used, `us_gaap` or `ifrs`.

## Years are not what you expect

Sixteen of these 28 companies end their fiscal year in January. Salesforce's "fiscal
2026" is the twelve months ending 31 January 2026, which is almost exactly
ServiceNow's calendar 2025. Across this set, one fiscal year label spans 335 days.

So a year range filters on **`year_basis=calendar`** by default, which lines companies
up against each other, and `year_basis=fiscal` is available for checking a number
against the filing it appears in. **Both labels are returned either way**, so neither
can mislead you.

One consequence worth knowing: no company files a fourth quarter. The annual report
covers the whole year instead. Fourth quarters here are derived as the year minus the
first nine months, marked `derived`, and only for concepts that can be added at all,
never for a ratio like earnings per share.

## Values are as filed

Unscaled, in the unit the row names: `USD`, `USD/shares` or `shares`. Rescaling into
millions would be the API quietly editing the data, so it does not.

## When not to use this

If you want everything rather than an answer, read the Parquet directly instead of
paging through JSON. The whole fact table is about 700 KB and one line of SQL reads
it:

```sql
select * from 'https://.../mart_financials.parquet' where ticker = 'CRM';
```

## Honest limits

- **28 companies, one sector.** Software and SaaS, because their revenue recognition
  is homogeneous enough to make reconciliation tractable. Banks and insurers are
  structurally different and are deliberately out of scope.
- **The mapping is a judgement**, informed by the filings' own linkbases where those
  exist. Most 10-Q calculation linkbases are not fetched, so a great many values are
  `unexamined` rather than confirmed.
- **Mislabelling is expected, not a failure.** That is why confidence is published on
  every value instead of presenting all mappings as equally certain. Ask
  `/confidence?trust=check` for the statements worth a human look.
