{#
  Keeps the equivalence mechanism visible after it stopped producing failures.

  Warns with the count of published values where a filer declares the tag a part of a
  total we map and its own figures make the part equal that total. Those used to be
  reported as contradictions. Now they are reported as what they are, and this test
  exists so the number is still in front of someone on every run.

  It warns rather than fails because every row is a value we are confident in. A
  warning of zero would be the interesting case: it would mean either that the arcs
  stopped being fetched or that the separation measurement stopped matching, and both
  are worth noticing. A test that can only ever pass teaches nothing, which is why
  this reports a count instead of asserting an absence.
#}

{{ config(severity='warn') }}

select
    ticker,
    concept,
    period_end,
    source_tag,
    value
from {{ ref('mart_financials') }}
where evidence = 'equivalent'
